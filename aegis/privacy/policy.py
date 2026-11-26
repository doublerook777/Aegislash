"""Policy loader for config/policy.yaml (stdlib only, no PyYAML dependency)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

DEFAULT_POLICY: dict[str, Any] = {
    "age_band_years": 5,
    "wide_age_band_years": 10,
    "elderly_age_threshold": 85,
    "date_shift_max_days": 180,
    "min_group_size": 5,
    "rare_condition_threshold": 3,
}

_DEFAULT_POLICY_PATH = Path(__file__).resolve().parents[2] / "config" / "policy.yaml"


def load_policy(path: Path | None = None) -> dict[str, Any]:
    """Load `key: value` settings from policy.yaml, merged onto safe defaults."""
    policy = dict(DEFAULT_POLICY)
    target = path if path is not None else _DEFAULT_POLICY_PATH
    if not target.exists():
        return policy
    for raw_line in target.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        k, v = (part.strip() for part in line.split(":", 1))
        if not k:
            continue
        if v.lstrip("-").isdigit():
            policy[k] = int(v)
        else:
            policy[k] = v
    return policy
