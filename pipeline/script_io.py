from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import ScriptDocument, ScriptScene


def load_script_file(path: Path) -> ScriptDocument:
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Script file does not exist: {path}")

    if path.suffix.lower() == ".json":
        return _load_json_script(path)

    return _load_text_script(path)


def _load_json_script(path: Path) -> ScriptDocument:
    payload = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(payload, dict) and "scenes" in payload:
        scene_source = payload["scenes"]
        metadata = {key: value for key, value in payload.items() if key != "scenes"}
    elif isinstance(payload, dict):
        scene_source = {key: value for key, value in payload.items() if isinstance(value, dict)}
        metadata = {key: value for key, value in payload.items() if not isinstance(value, dict)}
    elif isinstance(payload, list):
        scene_source = payload
        metadata = {}
    else:
        raise ValueError("JSON script must be an object or a list of scene definitions.")

    scenes = _normalize_json_scenes(scene_source, path)
    if not scenes:
        raise ValueError("JSON script does not contain any scenes.")

    return ScriptDocument(
        source_path=str(path),
        format="json",
        scenes=scenes,
        metadata=metadata,
    )


def _load_text_script(path: Path) -> ScriptDocument:
    text = path.read_text(encoding="utf-8").strip()
    segments = _split_text_script(text)
    if not segments:
        raise ValueError("The script is empty.")

    scenes = [
        ScriptScene(
            name=f"Scene {index}",
            description=segment,
        )
        for index, segment in enumerate(segments, start=1)
    ]

    return ScriptDocument(
        source_path=str(path),
        format="text",
        scenes=scenes,
    )


def _normalize_json_scenes(scene_source: Any, path: Path) -> list[ScriptScene]:
    if isinstance(scene_source, dict):
        return [
            _scene_from_mapping(scene_name, scene_payload, path)
            for scene_name, scene_payload in scene_source.items()
        ]

    if isinstance(scene_source, list):
        scenes: list[ScriptScene] = []
        for index, scene_payload in enumerate(scene_source, start=1):
            if isinstance(scene_payload, dict):
                scene_name = str(
                    scene_payload.get("name")
                    or scene_payload.get("scene")
                    or scene_payload.get("title")
                    or f"Scene {index}"
                )
            else:
                scene_name = f"Scene {index}"
            scenes.append(_scene_from_mapping(scene_name, scene_payload, path))
        return scenes

    raise ValueError("The JSON script scene container must be a dictionary or a list.")


def _scene_from_mapping(scene_name: str, scene_payload: Any, path: Path) -> ScriptScene:
    if isinstance(scene_payload, str):
        scene_payload = {"description": scene_payload}

    if not isinstance(scene_payload, dict):
        raise ValueError(f"Scene '{scene_name}' in {path.name} must be an object or string.")

    normalized = {_normalize_key(key): value for key, value in scene_payload.items()}

    description = _first_text(
        normalized,
        "description",
        "narration",
        "summary",
        "prompt",
        "visual_direction",
    )
    if not description:
        raise ValueError(f"Scene '{scene_name}' in {path.name} is missing a description-like field.")

    time_start = _first_text(normalized, "time_start", "start_time", "start")
    time_end = _first_text(normalized, "time_end", "end_time", "end")
    duration = _first_text(normalized, "duration")
    duration_s = _duration_to_seconds(duration)

    if duration_s is None and time_start and time_end:
        duration_s = _derive_duration_from_times(time_start, time_end)

    text_overlay = _first_text(normalized, "text_overlay", "overlay_text", "caption", "text")
    transition = _first_text(normalized, "transition")
    reference_image = _first_text(normalized, "reference_image", "image", "frame")

    consumed_keys = {
        "description",
        "narration",
        "summary",
        "prompt",
        "visual_direction",
        "time_start",
        "start_time",
        "start",
        "time_end",
        "end_time",
        "end",
        "duration",
        "text_overlay",
        "overlay_text",
        "caption",
        "text",
        "transition",
        "reference_image",
        "image",
        "frame",
        "name",
        "scene",
        "title",
    }
    metadata = {
        key: value
        for key, value in scene_payload.items()
        if _normalize_key(key) not in consumed_keys
    }

    if reference_image:
        reference_path = Path(reference_image).expanduser()
        if not reference_path.is_absolute():
            reference_path = path.parent / reference_path
        reference_image = str(reference_path.resolve())

    return ScriptScene(
        name=scene_name,
        description=description,
        time_start=time_start,
        time_end=time_end,
        duration=duration,
        duration_s=duration_s,
        text_overlay=text_overlay,
        transition=transition,
        reference_image=reference_image,
        metadata=metadata,
    )


def _split_text_script(text: str) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []

    line_based = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if len(line_based) > 1:
        return line_based

    return [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", cleaned) if segment.strip()]


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


def _first_text(mapping: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if value is None:
            continue
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
        else:
            return str(value)
    return None


def _duration_to_seconds(value: str | None) -> float | None:
    if not value:
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    labeled_match = re.fullmatch(
        r"(?:(?P<h>\d+)h:)?(?:(?P<m>\d+)m:)?(?:(?P<s>\d+)s:)?(?:(?P<ms>\d+)ms)?",
        cleaned,
    )
    if labeled_match:
        hours = int(labeled_match.group("h") or 0)
        minutes = int(labeled_match.group("m") or 0)
        seconds = int(labeled_match.group("s") or 0)
        milliseconds = int(labeled_match.group("ms") or 0)
        return hours * 3600 + minutes * 60 + seconds + (milliseconds / 1000.0)

    colon_match = re.fullmatch(r"(?P<h>\d+):(?P<m>\d+):(?P<s>\d+)(?:\.(?P<ms>\d+))?", cleaned)
    if colon_match:
        hours = int(colon_match.group("h") or 0)
        minutes = int(colon_match.group("m") or 0)
        seconds = int(colon_match.group("s") or 0)
        milliseconds = int((colon_match.group("ms") or "0").ljust(3, "0")[:3])
        return hours * 3600 + minutes * 60 + seconds + (milliseconds / 1000.0)

    try:
        return float(cleaned)
    except ValueError:
        return None


def _derive_duration_from_times(start: str, end: str) -> float | None:
    start_s = _duration_to_seconds(start)
    end_s = _duration_to_seconds(end)
    if start_s is None or end_s is None or end_s < start_s:
        return None
    return end_s - start_s
