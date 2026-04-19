from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    return normalized.strip("-") or "asset"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(_to_jsonable(payload), handle, indent=2)
    return path


def _to_jsonable(payload: Any) -> Any:
    if is_dataclass(payload):
        return asdict(payload)
    if isinstance(payload, Path):
        return str(payload)
    if isinstance(payload, list):
        return [_to_jsonable(item) for item in payload]
    if isinstance(payload, dict):
        return {key: _to_jsonable(value) for key, value in payload.items()}
    return payload
