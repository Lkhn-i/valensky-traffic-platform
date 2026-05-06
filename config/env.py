from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
_MISSING = object()


class EnvError(RuntimeError):
    """Raised when required environment configuration is missing."""


def load_env_file(path: Path | None = None) -> None:
    env_file = path or ROOT_DIR / ".env"
    if not env_file.exists():
        return

    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        cleaned = value.strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), cleaned)


def env_str(name: str, default: object = _MISSING) -> str:
    value = os.environ.get(name)
    if value is not None:
        return value
    if default is not _MISSING:
        return str(default)
    raise EnvError(f"Missing required environment variable: {name}")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int | None = None) -> int:
    value = os.environ.get(name)
    if value is None:
        if default is None:
            raise EnvError(f"Missing required integer environment variable: {name}")
        return default
    return int(value)


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.environ.get(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


load_env_file()
