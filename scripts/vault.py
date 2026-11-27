#!/usr/bin/env python3
"""Encrypted-at-rest copy of a raw input tree (AES-256-GCM envelope encryption).

    pip install -r requirements-vault.txt
    python scripts/vault.py keygen --key-file /secure/place/master.key
    python scripts/vault.py seal --input RAW_DIR --vault VAULT_DIR --key-file /secure/place/master.key
    python scripts/vault.py open --vault VAULT_DIR --output NEW_DIR --key-file /secure/place/master.key

Every file gets its own random data key, which is stored wrapped by the master key. Blobs have random
names; the original paths (they can hold patient names) are kept only in an encrypted manifest. The master
key must live outside the data, the vault and this repository.

This is a separate tool: ``main.py`` does not use it. It reads the input and never changes or deletes it.
It does not protect the original files, replace a key manager or cover memory swapped to disk. The number
of files and their approximate sizes stay visible. Messages never contain file names or file contents.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path, PurePosixPath

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

REPO = Path(__file__).resolve().parents[1]
MAGIC = b"AGV1"
KEY_LEN = 32
NONCE_LEN = 12
WRAPPED_LEN = KEY_LEN + 16  # data key + GCM tag
MANIFEST = "manifest.enc"


class VaultError(Exception):
    """Carries a fixed, PII-free error code."""


def _inside(path: Path, parent: Path) -> bool:
    path, parent = path.resolve(), parent.resolve()
    return path == parent or parent in path.parents


def _check_key_place(key_file: Path, *data_dirs: Path) -> None:
    if any(_inside(key_file, d) for d in (REPO, *data_dirs)):
        raise VaultError("key_must_be_outside_data_and_repo")


def _load_key(key_file: Path) -> bytes:
    key = key_file.read_bytes()
    if len(key) != KEY_LEN:
        raise VaultError("bad_key_file")
    return key


def _write_new(path: Path, data: bytes) -> None:
    """Create ``path`` readable by the owner only; never overwrite."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def _require_empty(directory: Path) -> None:
    if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
        raise VaultError("target_not_empty")


def _encrypt(master: bytes, name: str, plain: bytes) -> bytes:
    aad = MAGIC + name.encode("ascii")  # binds a blob to its name, so blobs cannot be swapped
    data_key = AESGCM.generate_key(bit_length=256)
    wrap_nonce, nonce = secrets.token_bytes(NONCE_LEN), secrets.token_bytes(NONCE_LEN)
    wrapped = AESGCM(master).encrypt(wrap_nonce, data_key, aad)
    return MAGIC + wrap_nonce + wrapped + nonce + AESGCM(data_key).encrypt(nonce, plain, aad)


def _decrypt(master: bytes, name: str, blob: bytes) -> bytes:
    aad = MAGIC + name.encode("ascii")
    a = len(MAGIC)
    b = a + NONCE_LEN
    c = b + WRAPPED_LEN
    d = c + NONCE_LEN
    if blob[:a] != MAGIC or len(blob) < d + 16:
        raise VaultError("not_a_vault_blob")
    try:
        data_key = AESGCM(master).decrypt(blob[a:b], blob[b:c], aad)
        return AESGCM(data_key).decrypt(blob[c:d], blob[d:], aad)
    except InvalidTag:
        raise VaultError("wrong_key_or_altered_data") from None


def keygen(key_file: Path) -> None:
    _check_key_place(key_file)
    if key_file.exists():
        raise VaultError("key_file_exists")
    _write_new(key_file, AESGCM.generate_key(bit_length=256))


def seal(input_dir: Path, vault_dir: Path, key_file: Path) -> int:
    if not input_dir.is_dir():
        raise VaultError("input_not_a_directory")
    if _inside(vault_dir, input_dir) or _inside(input_dir, vault_dir):
        raise VaultError("vault_and_input_overlap")
    _check_key_place(key_file, input_dir, vault_dir)
    master = _load_key(key_file)
    _require_empty(vault_dir)

    entries = sorted(input_dir.rglob("*"))
    # A link or special file would be left out of the copy without notice, so refuse the whole run.
    if any(p.is_symlink() or not (p.is_file() or p.is_dir()) for p in entries):
        raise VaultError("unsupported_file_type_in_input")
    files = [p for p in entries if p.is_file()]
    if not files:
        raise VaultError("input_has_no_files")

    vault_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    manifest: dict[str, str] = {}
    for path in files:
        name = secrets.token_hex(16) + ".enc"
        _write_new(vault_dir / name, _encrypt(master, name, path.read_bytes()))
        manifest[name] = path.relative_to(input_dir).as_posix()
    # Written last: an interrupted run leaves a vault that cannot be opened as complete.
    _write_new(vault_dir / MANIFEST, _encrypt(master, MANIFEST, json.dumps(manifest).encode("ascii")))
    return len(files)


def open_vault(vault_dir: Path, output_dir: Path, key_file: Path) -> int:
    if _inside(output_dir, vault_dir) or _inside(vault_dir, output_dir):
        raise VaultError("vault_and_output_overlap")
    _check_key_place(key_file, vault_dir, output_dir)
    master = _load_key(key_file)
    _require_empty(output_dir)
    manifest = json.loads(_decrypt(master, MANIFEST, (vault_dir / MANIFEST).read_bytes()))

    # Decrypt and check everything before the first plaintext byte reaches the disk.
    restored: list[tuple[PurePosixPath, bytes]] = []
    for name, rel_text in sorted(manifest.items()):
        rel = PurePosixPath(rel_text)
        if rel.is_absolute() or ".." in rel.parts or Path(name).name != name:
            raise VaultError("unsafe_path_in_manifest")
        blob = vault_dir / name
        if not blob.is_file():
            raise VaultError("blob_missing")
        restored.append((rel, _decrypt(master, name, blob.read_bytes())))

    output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    for rel, plain in restored:
        target = output_dir.joinpath(*rel.parts)
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        _write_new(target, plain)
    return len(restored)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Encrypted-at-rest copy of a raw input tree.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for cmd, dirs in (("keygen", ()), ("seal", ("--input", "--vault")), ("open", ("--vault", "--output"))):
        p = sub.add_parser(cmd)
        for flag in (*dirs, "--key-file"):
            p.add_argument(flag, required=True, type=Path)
    args = ap.parse_args(argv)
    try:
        if args.cmd == "keygen":
            keygen(args.key_file)
            print("key created")
        elif args.cmd == "seal":
            print(f"files sealed {seal(args.input, args.vault, args.key_file)}")
        else:
            print(f"files restored {open_vault(args.vault, args.output, args.key_file)}")
    except VaultError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # type only: messages can hold paths with patient names
        print(f"error: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
