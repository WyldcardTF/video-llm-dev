from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import SceneReferenceAsset, ScriptDocument, ScriptScene


IMAGE_EXTENSIONS = {
    ".bmp",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}
VIDEO_EXTENSIONS = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
}


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

    scenes = _normalize_json_scenes(scene_source, path, metadata)
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


def _normalize_json_scenes(scene_source: Any, path: Path, metadata: dict[str, Any]) -> list[ScriptScene]:
    global_reference_assets = _global_reference_assets(metadata)
    if isinstance(scene_source, dict):
        return [
            _scene_from_mapping(scene_name, scene_payload, path, global_reference_assets)
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
            scenes.append(_scene_from_mapping(scene_name, scene_payload, path, global_reference_assets))
        return scenes

    raise ValueError("The JSON script scene container must be a dictionary or a list.")


def _scene_from_mapping(
    scene_name: str,
    scene_payload: Any,
    path: Path,
    global_reference_assets: Any,
) -> ScriptScene:
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
    reference_assets = _normalize_reference_assets(
        scene_name,
        normalized,
        path,
        global_reference_assets,
    )

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
        "reference_images",
        "reference_assets",
        "supporting_assets",
        "supporting_data",
        "general_assets_images",
        "general_assets_video",
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
        reference_assets=reference_assets,
        metadata=metadata,
    )


def _normalize_reference_assets(
    scene_name: str,
    normalized: dict[str, Any],
    path: Path,
    global_reference_assets: Any,
) -> list[SceneReferenceAsset]:
    references: list[SceneReferenceAsset] = []
    disabled_paths: set[str] = set()

    for source_field in ("reference_assets", "supporting_assets", "supporting_data"):
        value = normalized.get(source_field)
        disabled_paths.update(_disabled_reference_paths_from_value(value, path))
        references.extend(_references_from_value(value, path, source_field=source_field))

    disabled_paths.update(_disabled_reference_paths_from_value(normalized.get("reference_images"), path))
    disabled_paths.update(_disabled_reference_paths_from_value(normalized.get("general_assets_images"), path))
    disabled_paths.update(_disabled_reference_paths_from_value(normalized.get("general_assets_video"), path))
    disabled_paths.update(_disabled_reference_paths_from_value(global_reference_assets, path))

    references.extend(
        _references_from_value(
            normalized.get("reference_images"),
            path,
            source_field="reference_images",
            default_role="asset",
            default_provider_use="reference_input",
        )
    )
    references.extend(
        _references_from_value(
            normalized.get("general_assets_images"),
            path,
            source_field="general_assets_images",
            default_role="asset",
            default_provider_use="reference_input",
            search_base=("general_assets", "images"),
        )
    )
    references.extend(
        _references_from_value(
            normalized.get("general_assets_video"),
            path,
            source_field="general_assets_video",
            default_role="motion_reference",
            default_provider_use="prompt_and_frame",
            search_base=("general_assets", "video"),
        )
    )
    references.extend(
        _references_from_value(
            global_reference_assets,
            path,
            source_field="global_style.general_reference_assets",
            default_role="global_context",
            default_provider_use="prompt_and_reference",
        )
    )
    references.extend(_auto_discover_supporting_references(scene_name, path))

    seen: set[str] = set()
    unique_references: list[SceneReferenceAsset] = []
    for reference in references:
        identity = reference.path
        if identity in seen or identity in disabled_paths:
            continue
        seen.add(identity)
        unique_references.append(reference)
    return unique_references


def _references_from_value(
    value: Any,
    script_path: Path,
    source_field: str,
    default_role: str = "asset",
    default_provider_use: str = "auto",
    search_base: tuple[str, ...] = (),
) -> list[SceneReferenceAsset]:
    if value in (None, ""):
        return []

    if isinstance(value, (str, Path)):
        items: list[Any] = [value]
    elif isinstance(value, list):
        items = value
    else:
        items = [value]

    references: list[SceneReferenceAsset] = []
    for item in items:
        if item in (None, ""):
            continue

        if isinstance(item, dict):
            if not _asset_is_enabled(item):
                continue
            raw_path = (
                item.get("path")
                or item.get("file")
                or item.get("asset")
                or item.get("image")
                or item.get("video")
                or item.get("url")
            )
            if not raw_path:
                continue
            role = str(item.get("role") or item.get("type") or default_role).strip() or default_role
            label = str(item.get("label") or item.get("name") or "").strip()
            prompt_hint = str(
                item.get("prompt_hint")
                or item.get("description")
                or item.get("notes")
                or ""
            ).strip()
            provider_use = str(
                item.get("provider_use")
                or item.get("use")
                or default_provider_use
            ).strip() or default_provider_use
            media_kind = _media_kind_from_asset_type(item.get("asset_type"))
        else:
            raw_path = str(item)
            role = default_role
            label = Path(str(item)).stem
            prompt_hint = ""
            provider_use = default_provider_use
            media_kind = None

        if _is_url(str(raw_path)):
            references.append(
                SceneReferenceAsset(
                    path=str(raw_path),
                    role=role,
                    label=label or Path(str(raw_path)).stem,
                    prompt_hint=prompt_hint,
                    provider_use=provider_use,
                    media_kind=media_kind or _media_kind_for_name(str(raw_path)),
                    source_field=source_field,
                )
            )
            continue

        for resolved_path in _expand_reference_path(str(raw_path), script_path, search_base):
            if not resolved_path.exists():
                continue
            references.append(
                SceneReferenceAsset(
                    path=str(resolved_path),
                    role=role,
                    label=label or resolved_path.stem,
                    prompt_hint=prompt_hint,
                    provider_use=provider_use,
                    media_kind=media_kind or _media_kind_for_path(resolved_path),
                    source_field=source_field,
                )
            )
    return references


def _disabled_reference_paths_from_value(
    value: Any,
    script_path: Path,
    search_base: tuple[str, ...] = (),
) -> set[str]:
    if value in (None, ""):
        return set()
    items = value if isinstance(value, list) else [value]

    disabled: set[str] = set()
    for item in items:
        if not isinstance(item, dict) or _asset_is_enabled(item):
            continue
        raw_path = (
            item.get("path")
            or item.get("file")
            or item.get("asset")
            or item.get("image")
            or item.get("video")
            or item.get("url")
        )
        if not raw_path:
            continue
        if _is_url(str(raw_path)):
            disabled.add(str(raw_path))
            continue
        for resolved_path in _expand_reference_path(str(raw_path), script_path, search_base):
            if resolved_path.exists():
                disabled.add(str(resolved_path))
    return disabled


def _global_reference_assets(metadata: dict[str, Any]) -> Any:
    global_style = metadata.get("global_style", {})
    if isinstance(global_style, dict) and "general_reference_assets" in global_style:
        return global_style.get("general_reference_assets")
    return metadata.get("general_reference_assets")


def _asset_is_enabled(item: dict[str, Any]) -> bool:
    value = item.get("use_asset", True)
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    return normalized not in {"0", "false", "no", "off", "skip", "disabled"}


def _media_kind_from_asset_type(value: Any) -> str | None:
    if value in (None, ""):
        return None
    normalized = str(value).strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"image", "images", "picture", "photo", "reference_image"}:
        return "image"
    if normalized in {"video", "videos", "movie", "clip", "reference_video"}:
        return "video"
    return None


def _expand_reference_path(
    raw_path: str,
    script_path: Path,
    search_base: tuple[str, ...],
) -> list[Path]:
    resolved = _resolve_reference_path(raw_path, script_path, search_base)
    if resolved.exists() and resolved.is_dir():
        allowed = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
        return sorted(
            file_path.resolve()
            for file_path in resolved.rglob("*")
            if file_path.is_file() and file_path.suffix.lower() in allowed
        )
    return [resolved.resolve()]


def _resolve_reference_path(
    raw_path: str,
    script_path: Path,
    search_base: tuple[str, ...],
) -> Path:
    candidate = Path(raw_path).expanduser()
    if candidate.is_absolute():
        return candidate

    project_root = script_path.parent.parent if script_path.parent.name.lower() == "scripts" else script_path.parent
    supporting_root = project_root / "Supporting Data"
    candidates = [
        script_path.parent / candidate,
        project_root / candidate,
        supporting_root / candidate,
    ]
    if search_base:
        candidates.append(supporting_root.joinpath(*search_base) / candidate)

    for candidate_path in candidates:
        if candidate_path.exists():
            return candidate_path
        case_match = _case_insensitive_existing_path(candidate_path)
        if case_match is not None:
            return case_match
    return candidates[-1]


def _auto_discover_supporting_references(scene_name: str, script_path: Path) -> list[SceneReferenceAsset]:
    project_root = script_path.parent.parent if script_path.parent.name.lower() == "scripts" else script_path.parent
    supporting_root = project_root / "Supporting Data"
    if not supporting_root.exists():
        return []

    scene_key = _folder_match_key(scene_name)
    allowed = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS
    references: list[SceneReferenceAsset] = []
    for folder in sorted(path for path in supporting_root.rglob("*") if path.is_dir()):
        folder_key = _folder_match_key(folder.name)
        if folder_key not in {"general", scene_key}:
            continue

        scope = "global" if folder_key == "general" else "scene"
        for file_path in sorted(folder.rglob("*")):
            if not file_path.is_file() or file_path.suffix.lower() not in allowed:
                continue
            media_kind = _media_kind_for_path(file_path)
            references.append(
                SceneReferenceAsset(
                    path=str(file_path.resolve()),
                    role="global_context" if scope == "global" else "scene_reference",
                    label=f"{scope} {file_path.stem}",
                    prompt_hint=(
                        "Use as context for the whole video."
                        if scope == "global"
                        else f"Use only for {scene_name}."
                    ),
                    provider_use="prompt_and_reference" if media_kind == "image" else "prompt_and_frame",
                    media_kind=media_kind,
                    source_field=f"auto_{scope}_folder",
                )
            )
    return references


def _case_insensitive_existing_path(path: Path) -> Path | None:
    if path.exists():
        return path
    parts = path.parts
    if not parts:
        return None

    current = Path(parts[0])
    start_index = 1
    if path.is_absolute():
        current = Path(path.anchor)
        start_index = 1

    for part in parts[start_index:]:
        if not current.exists() or not current.is_dir():
            return None
        matches = [child for child in current.iterdir() if child.name.lower() == part.lower()]
        if not matches:
            return None
        current = matches[0]
    return current if current.exists() else None


def _folder_match_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.strip().lower())


def _media_kind_for_path(path: Path) -> str | None:
    return _media_kind_for_name(str(path))


def _media_kind_for_name(value: str) -> str | None:
    suffix = Path(value).suffix.lower()
    if "?" in suffix:
        suffix = suffix.split("?", 1)[0]
    if "#" in suffix:
        suffix = suffix.split("#", 1)[0]
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return None


def _is_url(value: str) -> bool:
    return bool(re.match(r"^https?://", value, flags=re.IGNORECASE))


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
