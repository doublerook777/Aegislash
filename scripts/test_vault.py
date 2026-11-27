"""Tests for scripts/vault.py. All data here is invented."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vault  # noqa: E402

FILES = {
    "notes/Testperson_Example.txt": "Name: Testperson Example, ph 9000000000\n".encode(),
    "ward.csv": "नाम,उम्र\nउदाहरण,40\n".encode("utf-16"),
    "empty.json": b"",
}


def _tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def setup(tmp_path: Path):
    raw = tmp_path / "raw"
    for rel, data in FILES.items():
        (raw / rel).parent.mkdir(parents=True, exist_ok=True)
        (raw / rel).write_bytes(data)
    key = tmp_path / "master.key"
    vault.keygen(key)
    return raw, tmp_path / "vault", key, tmp_path / "restored"


def _blobs(box: Path) -> list[Path]:
    return sorted(p for p in box.iterdir() if p.name != vault.MANIFEST)


def test_round_trip_is_byte_identical_and_input_is_unchanged(setup):
    raw, box, key, out = setup
    assert vault.seal(raw, box, key) == len(FILES)
    assert vault.open_vault(box, out, key) == len(FILES)
    assert _tree(out) == FILES
    assert _tree(raw) == FILES


def test_vault_shows_no_names_or_contents(setup):
    raw, box, key, _ = setup
    vault.seal(raw, box, key)
    for path in box.rglob("*"):
        assert "Testperson" not in path.name
        data = path.read_bytes()
        assert b"Testperson" not in data and b"9000000000" not in data


def test_key_and_vault_are_owner_only(setup):
    raw, box, key, _ = setup
    vault.seal(raw, box, key)
    assert key.stat().st_mode & 0o077 == 0
    assert all(p.stat().st_mode & 0o077 == 0 for p in [box, *box.iterdir()])


def _assert_refused(box, out, key, code):
    with pytest.raises(vault.VaultError, match=code):
        vault.open_vault(box, out, key)
    assert not out.exists()  # nothing partial is written


def test_wrong_key_is_rejected(setup, tmp_path):
    raw, box, key, out = setup
    vault.seal(raw, box, key)
    other = tmp_path / "other.key"
    vault.keygen(other)
    _assert_refused(box, out, other, "wrong_key_or_altered_data")


def test_altered_blob_is_rejected(setup):
    raw, box, key, out = setup
    vault.seal(raw, box, key)
    blob = _blobs(box)[-1]
    data = bytearray(blob.read_bytes())
    data[-1] ^= 1
    blob.write_bytes(bytes(data))
    _assert_refused(box, out, key, "wrong_key_or_altered_data")


def test_swapped_blobs_are_rejected(setup):
    raw, box, key, out = setup
    vault.seal(raw, box, key)
    first, second = _blobs(box)[:2]
    a, b = first.read_bytes(), second.read_bytes()
    first.write_bytes(b)
    second.write_bytes(a)
    _assert_refused(box, out, key, "wrong_key_or_altered_data")


def test_missing_blob_is_rejected(setup):
    raw, box, key, out = setup
    vault.seal(raw, box, key)
    _blobs(box)[0].unlink()
    _assert_refused(box, out, key, "blob_missing")


def test_key_inside_data_vault_or_repo_is_refused(setup):
    raw, box, key, _ = setup
    for bad in (raw / "k.key", box / "k.key", vault.REPO / "k.key"):
        with pytest.raises(vault.VaultError, match="key_must_be_outside"):
            vault.seal(raw, box, bad)
    with pytest.raises(vault.VaultError, match="key_must_be_outside"):
        vault.keygen(vault.REPO / "k.key")
    assert not (vault.REPO / "k.key").exists()


def test_never_overwrites(setup):
    raw, box, key, _ = setup
    with pytest.raises(vault.VaultError, match="key_file_exists"):
        vault.keygen(key)
    vault.seal(raw, box, key)
    with pytest.raises(vault.VaultError, match="target_not_empty"):
        vault.seal(raw, box, key)
    with pytest.raises(vault.VaultError, match="vault_and_input_overlap"):
        vault.seal(raw, raw / "vault", key)


def test_symlink_in_input_is_refused(setup):
    raw, box, key, _ = setup
    (raw / "link.txt").symlink_to(key)
    with pytest.raises(vault.VaultError, match="unsupported_file_type"):
        vault.seal(raw, box, key)
    assert not box.exists()


def test_errors_never_print_file_names(setup, capsys):
    raw, box, key, _ = setup
    code = vault.main(["seal", "--input", str(raw / "Testperson_Missing"), "--vault", str(box),
                       "--key-file", str(key)])
    code2 = vault.main(["open", "--vault", str(raw / "Testperson_Missing"), "--output", str(box),
                        "--key-file", str(key)])
    seen = capsys.readouterr()
    assert code == code2 == 1
    assert "Testperson" not in seen.out + seen.err
