from __future__ import annotations

from collections import Counter
from pathlib import Path

import cv2

from .config import Settings
from .ingest import VIDEO_EXTENSIONS
from .io_utils import read_json, slugify
from .models import AssetCandidate, AssetInventory, VideoAnalysis
from .run_config import RunParameters


IMAGE_EXTENSIONS = {
    ".bmp",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def build_asset_inventory(
    run_parameters: RunParameters,
    settings: Settings,
    analyses: list[VideoAnalysis],
) -> AssetInventory:
    root = run_parameters.input_root(settings).resolve()
    asset_paths = _sorted_asset_paths(run_parameters)
    items: list[AssetCandidate] = []
    seen_paths: set[Path] = set()

    for analysis in analyses:
        source_path = Path(analysis.source_path).expanduser().resolve()
        seen_paths.add(source_path)
        asset_type = _match_asset_type(source_path, root, asset_paths)
        items.append(
            AssetCandidate(
                asset_id=slugify(f"{asset_type}-{source_path.stem}"),
                asset_type=asset_type,
                media_kind="video",
                path=str(source_path),
                width=analysis.width,
                height=analysis.height,
                duration_s=analysis.duration_s,
                tags=_path_tags(source_path, root),
            )
        )

    if not run_parameters.selection.use_input_images:
        summary = Counter(f"{item.asset_type}:{item.media_kind}" for item in items)
        return AssetInventory(
            items=items,
            summary=dict(sorted(summary.items())),
        )

    for asset_type, relative_path in asset_paths:
        asset_root = (root / relative_path).resolve()
        if not asset_root.exists():
            continue

        for file_path in sorted(asset_root.rglob("*")):
            if not file_path.is_file():
                continue
            resolved_path = file_path.resolve()
            if resolved_path in seen_paths:
                continue
            suffix = resolved_path.suffix.lower()
            if suffix not in IMAGE_EXTENSIONS:
                continue

            width, height = _image_dimensions(resolved_path)
            items.append(
                AssetCandidate(
                    asset_id=slugify(f"{asset_type}-{resolved_path.stem}"),
                    asset_type=asset_type,
                    media_kind="image",
                    path=str(resolved_path),
                    width=width,
                    height=height,
                    tags=_path_tags(resolved_path, root),
                )
            )
            seen_paths.add(resolved_path)

    summary = Counter(f"{item.asset_type}:{item.media_kind}" for item in items)
    return AssetInventory(
        items=items,
        summary=dict(sorted(summary.items())),
    )


def load_asset_inventory(path: Path) -> AssetInventory:
    payload = read_json(path.expanduser().resolve())
    if not isinstance(payload, dict):
        raise ValueError(f"Asset inventory file must contain a JSON object: {path}")

    items: list[AssetCandidate] = []
    for raw_item in payload.get("items", []):
        if not isinstance(raw_item, dict):
            continue
        items.append(
            AssetCandidate(
                asset_id=str(raw_item.get("asset_id", "")),
                asset_type=str(raw_item.get("asset_type", "misc")),
                media_kind=str(raw_item.get("media_kind", "other")),
                path=str(raw_item.get("path", "")),
                width=_optional_int(raw_item.get("width")),
                height=_optional_int(raw_item.get("height")),
                duration_s=_optional_float(raw_item.get("duration_s")),
                tags=[str(tag) for tag in raw_item.get("tags", [])],
            )
        )

    summary = payload.get("summary", {})
    if not isinstance(summary, dict):
        summary = {}

    return AssetInventory(
        items=items,
        summary={str(key): int(value) for key, value in summary.items()},
    )


def _sorted_asset_paths(run_parameters: RunParameters) -> list[tuple[str, Path]]:
    return sorted(
        (
            (asset_type, Path(relative_path))
            for asset_type, relative_path in run_parameters.asset_subfolders.items()
        ),
        key=lambda item: (-len(item[1].parts), item[0]),
    )


def _match_asset_type(
    source_path: Path,
    input_root: Path,
    asset_paths: list[tuple[str, Path]],
) -> str:
    for asset_type, relative_path in asset_paths:
        asset_root = (input_root / relative_path).resolve()
        try:
            source_path.relative_to(asset_root)
            return asset_type
        except ValueError:
            continue
    return "bundle_videos" if source_path.suffix.lower() in VIDEO_EXTENSIONS else "misc"


def _path_tags(path: Path, input_root: Path) -> list[str]:
    try:
        relative_parts = path.relative_to(input_root).parts[:-1]
    except ValueError:
        relative_parts = path.parts[:-1]
    cleaned = [slugify(part).replace("-", "_") for part in relative_parts if part]
    return list(dict.fromkeys(tag for tag in cleaned if tag))


def _image_dimensions(path: Path) -> tuple[int | None, int | None]:
    image = cv2.imread(str(path))
    if image is None:
        return None, None
    height, width = image.shape[:2]
    return width, height


def _optional_int(value: object) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
