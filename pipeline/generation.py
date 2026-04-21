from __future__ import annotations

import urllib.parse
from dataclasses import replace
from pathlib import Path
from typing import Any

import cv2

from .config import Settings
from .ingest import VIDEO_EXTENSIONS
from .io_utils import ensure_dir
from .models import (
    GeneratedAssetManifest,
    GeneratedAssetRecord,
    GenerationPlan,
    SceneReferenceAsset,
    ShotPlanItem,
    StyleProfile,
)
from .run_config import RunParameters
from .video_models import VideoModelSelection, resolve_video_model_selection
from .video_providers import (
    PreparedReference,
    VideoGenerationRequest,
    get_video_provider,
)


IMAGE_EXTENSIONS = {
    ".bmp",
    ".jpeg",
    ".jpg",
    ".png",
    ".tif",
    ".tiff",
    ".webp",
}


def resolve_generation_backend(run_parameters: RunParameters) -> str:
    return resolve_video_model_selection(run_parameters).provider


def generate_assets_for_plan(
    plan: GenerationPlan,
    style_profile: StyleProfile,
    run_parameters: RunParameters,
    settings: Settings,
    project_dir: Path,
) -> tuple[GenerationPlan, GeneratedAssetManifest]:
    model_selection = resolve_video_model_selection(run_parameters)
    provider = get_video_provider(model_selection.provider)
    output_dir = ensure_dir(settings.generated_assets_dir(project_dir))
    manifest = GeneratedAssetManifest(
        backend=model_selection.provider,
        output_dir=str(output_dir),
    )
    updated_items: list[ShotPlanItem] = []

    for item in plan.items:
        updated_item, record = _generate_video_asset(
            provider=provider,
            item=item,
            style_profile=style_profile,
            run_parameters=run_parameters,
            settings=settings,
            output_dir=output_dir,
            model_selection=model_selection,
        )
        updated_items.append(updated_item)
        manifest.items.append(record)

    return replace(plan, items=updated_items, generation_backend=model_selection.provider), manifest


def _generate_video_asset(
    provider: object,
    item: ShotPlanItem,
    style_profile: StyleProfile,
    run_parameters: RunParameters,
    settings: Settings,
    output_dir: Path,
    model_selection: VideoModelSelection,
) -> tuple[ShotPlanItem, GeneratedAssetRecord]:
    output_path = output_dir / f"shot_{item.index:03d}.mp4"
    size = _derive_video_size(style_profile, run_parameters, model_selection)
    aspect_ratio = _derive_aspect_ratio(style_profile, run_parameters, model_selection, size)
    resolution = _derive_resolution(run_parameters, model_selection)
    seconds = _derive_video_seconds(item.duration_s, model_selection, run_parameters)
    references = _prepare_references(
        item=item,
        run_parameters=run_parameters,
        settings=settings,
        output_dir=output_dir,
        size=size,
        provider_name=model_selection.provider,
    )
    prompt = _build_backend_prompt(item, references, model_selection)

    request = VideoGenerationRequest(
        prompt=prompt,
        negative_prompt=item.negative_prompt or "",
        output_path=output_path,
        model_selection=model_selection,
        run_parameters=run_parameters,
        settings=settings,
        duration_seconds=seconds,
        size=size,
        aspect_ratio=aspect_ratio,
        resolution=resolution,
        references=references,
        provider_options=_provider_options_for_item(item),
    )
    result = provider.generate(request)  # type: ignore[attr-defined]

    updated_item = replace(
        item,
        source_asset_path=str(result.asset_path),
        source_asset_type="generated_video",
        media_kind="video",
        clip_start_s=0.0,
        clip_duration_s=min(float(seconds), item.duration_s),
        motion_strategy="generated_video",
    )
    record = GeneratedAssetRecord(
        shot_index=item.index,
        backend=model_selection.provider,
        media_kind="video",
        status="generated",
        asset_path=str(result.asset_path),
        model=model_selection.model,
        model_preset=model_selection.preset_id,
        source_asset_path=item.source_asset_path,
        reference_asset_paths=result.used_reference_paths,
        prompt=prompt,
        revised_prompt=result.revised_prompt,
        remote_id=result.remote_id,
    )
    return updated_item, record


def _build_backend_prompt(
    item: ShotPlanItem,
    references: list[PreparedReference],
    model_selection: VideoModelSelection,
) -> str:
    positive = item.generation_prompt or item.visual_direction or item.narration
    prompt = positive.strip()
    if references:
        prompt += " Supporting references: "
        prompt += "; ".join(
            _reference_prompt_text(reference)
            for reference in references
        )
        prompt += "."
    prompt += (
        f" Render as a newly generated animated/cinematic video clip, not a still image. "
        f"Provider target: {model_selection.label}."
    )
    return prompt.strip()


def _reference_prompt_text(reference: PreparedReference) -> str:
    parts = [
        f"role={reference.role}",
        f"label={reference.label}",
    ]
    if reference.prompt_hint:
        parts.append(f"meaning={reference.prompt_hint}")
    if reference.provider_use:
        parts.append(f"use={reference.provider_use}")
    return ", ".join(parts)


def _provider_options_for_item(item: ShotPlanItem) -> dict[str, Any]:
    value = item.scene_metadata.get("provider_options")
    if isinstance(value, dict):
        return value
    kling_value = item.scene_metadata.get("kling")
    if isinstance(kling_value, dict):
        return {"kling": kling_value}
    return {}


def _prepare_references(
    item: ShotPlanItem,
    run_parameters: RunParameters,
    settings: Settings,
    output_dir: Path,
    size: str | None,
    provider_name: str,
) -> list[PreparedReference]:
    if not run_parameters.generation.use_reference_input:
        return []

    raw_references = list(item.reference_assets)
    if item.reference_image:
        raw_references.append(
            SceneReferenceAsset(
                path=item.reference_image,
                role="asset",
                label="script reference image",
                provider_use="reference_input",
                media_kind="image",
                source_field="reference_image",
            )
        )
    if item.source_asset_path:
        raw_references.append(
            SceneReferenceAsset(
                path=item.source_asset_path,
                role="motion_reference" if item.media_kind == "video" else "asset",
                label=item.source_asset_type or "selected asset",
                provider_use="prompt_and_frame",
                media_kind=item.media_kind,
                source_field="selected_asset",
            )
        )

    limit = max(run_parameters.generation.reference_asset_limit, 1)
    prepared: list[PreparedReference] = []
    for reference in raw_references:
        if len(prepared) >= limit:
            break
        prepared_reference = _prepare_single_reference(
            reference=reference,
            item=item,
            run_parameters=run_parameters,
            settings=settings,
            output_dir=output_dir,
            size=size,
            provider_name=provider_name,
            reference_index=len(prepared) + 1,
        )
        if prepared_reference is None:
            continue
        prepared.append(prepared_reference)
    return prepared


def _prepare_single_reference(
    reference: SceneReferenceAsset,
    item: ShotPlanItem,
    run_parameters: RunParameters,
    settings: Settings,
    output_dir: Path,
    size: str | None,
    provider_name: str,
    reference_index: int,
) -> PreparedReference | None:
    if reference.path.startswith(("http://", "https://")):
        return PreparedReference(
            path=reference.path,
            role=reference.role,
            label=reference.label or f"reference {reference_index}",
            prompt_hint=reference.prompt_hint,
            provider_use=reference.provider_use,
            media_kind=reference.media_kind,
            url=reference.path,
            mime_type=None,
        )

    path = Path(reference.path).expanduser().resolve()
    if not path.exists():
        return None

    media_kind = reference.media_kind or _media_kind_for_path(path)
    prepared_path = path
    mime_type = _mime_type_for_path(path)

    if (
        media_kind == "image"
        and provider_name == "kling"
        and run_parameters.generation.kling_fit_reference_images
        and run_parameters.generation.kling_local_image_transport.strip().lower() == "base64"
    ):
        prepared_path = _fit_image_reference_to_aspect(
            path=prepared_path,
            output_dir=output_dir,
            shot_index=item.index,
            reference_index=reference_index,
            aspect_ratio=run_parameters.generation.video_aspect_ratio,
            resolution=run_parameters.generation.video_resolution,
        )
        mime_type = "image/png"

    return PreparedReference(
        path=str(prepared_path),
        role=reference.role,
        label=reference.label or prepared_path.stem,
        prompt_hint=reference.prompt_hint,
        provider_use=reference.provider_use,
        media_kind=media_kind,
        url=_public_url_for_path(prepared_path, run_parameters, settings),
        mime_type=mime_type,
    )


def _prepare_future_video_input_reference(
    item: ShotPlanItem,
    output_dir: Path,
) -> Path | None:
    """Scaffold for future video-to-video providers.

    The current Kling path intentionally does not use source video as an input.
    When we add video-conditioned generation later, this helper can trim the
    selected source video to the planned shot window and return that clip.
    """
    if item.media_kind != "video" or not item.source_asset_path:
        return None

    source_path = Path(item.source_asset_path).expanduser().resolve()
    if not source_path.exists() or source_path.suffix.lower() not in VIDEO_EXTENSIONS:
        return None

    # Not called today. Kept as the single future hook for video-input prep.
    return output_dir / f"shot_{item.index:03d}_future_video_reference.mp4"


def _extract_reference_frame(
    path: Path,
    output_dir: Path,
    shot_index: int,
    reference_index: int,
    clip_start_s: float,
) -> Path:
    output_path = output_dir / f"shot_{shot_index:03d}_reference_{reference_index:02d}.png"
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return path
    fps = capture.get(cv2.CAP_PROP_FPS) or 24.0
    capture.set(cv2.CAP_PROP_POS_FRAMES, max(int(clip_start_s * fps), 0))
    success, frame = capture.read()
    capture.release()
    if not success or frame is None:
        return path
    cv2.imwrite(str(output_path), frame)
    return output_path


def _resize_image_reference(
    path: Path,
    output_dir: Path,
    shot_index: int,
    reference_index: int,
    size: str,
) -> Path:
    dimensions = _parse_size(size)
    if dimensions is None:
        return path
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return path
    width, height = dimensions
    resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
    output_path = output_dir / f"shot_{shot_index:03d}_reference_{reference_index:02d}_sized.png"
    cv2.imwrite(str(output_path), resized)
    return output_path


def _fit_image_reference_to_aspect(
    path: Path,
    output_dir: Path,
    shot_index: int,
    reference_index: int,
    aspect_ratio: str | None,
    resolution: str | None,
) -> Path:
    dimensions = _dimensions_for_aspect_resolution(aspect_ratio, resolution)
    if dimensions is None:
        return path
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        return path

    target_width, target_height = dimensions
    source_height, source_width = image.shape[:2]
    if source_width <= 0 or source_height <= 0:
        return path

    scale = min(target_width / source_width, target_height / source_height)
    fitted_width = max(int(round(source_width * scale)), 1)
    fitted_height = max(int(round(source_height * scale)), 1)
    fitted = cv2.resize(image, (fitted_width, fitted_height), interpolation=cv2.INTER_AREA)

    cover_scale = max(target_width / source_width, target_height / source_height)
    cover_width = max(int(round(source_width * cover_scale)), 1)
    cover_height = max(int(round(source_height * cover_scale)), 1)
    background = cv2.resize(image, (cover_width, cover_height), interpolation=cv2.INTER_AREA)
    offset_x = max((cover_width - target_width) // 2, 0)
    offset_y = max((cover_height - target_height) // 2, 0)
    canvas = background[offset_y:offset_y + target_height, offset_x:offset_x + target_width]
    canvas = cv2.GaussianBlur(canvas, (0, 0), sigmaX=18, sigmaY=18)
    canvas = cv2.convertScaleAbs(canvas, alpha=0.72, beta=18)

    paste_x = (target_width - fitted_width) // 2
    paste_y = (target_height - fitted_height) // 2
    canvas[paste_y:paste_y + fitted_height, paste_x:paste_x + fitted_width] = fitted

    output_path = output_dir / f"shot_{shot_index:03d}_reference_{reference_index:02d}_kling_fit.png"
    cv2.imwrite(str(output_path), canvas)
    return output_path


def _dimensions_for_aspect_resolution(
    aspect_ratio: str | None,
    resolution: str | None,
) -> tuple[int, int] | None:
    ratio = (aspect_ratio or "9:16").strip()
    if ":" not in ratio:
        return None
    width_text, height_text = ratio.split(":", 1)
    try:
        ratio_width = int(width_text)
        ratio_height = int(height_text)
    except ValueError:
        return None
    if ratio_width <= 0 or ratio_height <= 0:
        return None

    short_side = 540
    cleaned_resolution = (resolution or "").strip().lower()
    if cleaned_resolution.endswith("p"):
        try:
            short_side = int(cleaned_resolution[:-1])
        except ValueError:
            short_side = 540

    if ratio_height >= ratio_width:
        width = short_side
        height = int(round(width * ratio_height / ratio_width))
    else:
        height = short_side
        width = int(round(height * ratio_width / ratio_height))
    return width, height


def _public_url_for_path(path: Path, run_parameters: RunParameters, settings: Settings) -> str | None:
    base_url = run_parameters.generation.public_asset_base_url
    if not base_url:
        return None
    try:
        relative = path.resolve().relative_to(run_parameters.input_root(settings).resolve())
    except ValueError:
        return None
    encoded = "/".join(urllib.parse.quote(part) for part in relative.parts)
    return f"{base_url.rstrip('/')}/{encoded}"


def _derive_video_size(
    style_profile: StyleProfile,
    run_parameters: RunParameters,
    model_selection: VideoModelSelection,
) -> str | None:
    if run_parameters.generation.video_size:
        return run_parameters.generation.video_size
    if model_selection.default_size:
        return model_selection.default_size
    width = style_profile.target_width
    height = style_profile.target_height
    if height > width:
        return "720x1280"
    return "1280x720"


def _derive_aspect_ratio(
    style_profile: StyleProfile,
    run_parameters: RunParameters,
    model_selection: VideoModelSelection,
    size: str | None,
) -> str | None:
    if run_parameters.generation.video_aspect_ratio:
        return run_parameters.generation.video_aspect_ratio
    if model_selection.default_aspect_ratio:
        return model_selection.default_aspect_ratio
    dimensions = _parse_size(size) if size else None
    if dimensions:
        width, height = dimensions
        return "9:16" if height > width else "16:9"
    return "9:16" if style_profile.target_height > style_profile.target_width else "16:9"


def _derive_resolution(
    run_parameters: RunParameters,
    model_selection: VideoModelSelection,
) -> str | None:
    return run_parameters.generation.video_resolution or model_selection.default_resolution or "720p"


def _derive_video_seconds(
    duration_s: float,
    model_selection: VideoModelSelection,
    run_parameters: RunParameters,
) -> int:
    requested = (
        run_parameters.generation.video_duration_seconds
        or model_selection.default_duration_seconds
        or int(round(duration_s))
    )
    requested = max(int(requested), 1)
    if model_selection.provider == "kling":
        return _closest_supported_duration(requested, [5, 10])
    return _closest_supported_duration(requested, [5, 10])


def _closest_supported_duration(requested: int, supported: list[int]) -> int:
    for value in supported:
        if requested <= value:
            return value
    return supported[-1]


def _parse_size(size: str | None) -> tuple[int, int] | None:
    if not size or "x" not in size:
        return None
    width_text, height_text = size.lower().split("x", 1)
    try:
        return int(width_text), int(height_text)
    except ValueError:
        return None


def _media_kind_for_path(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    return None


def _mime_type_for_path(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".webp":
        return "image/webp"
    if suffix in VIDEO_EXTENSIONS:
        return "video/mp4" if suffix == ".mp4" else f"video/{suffix.lstrip('.')}"
    return None
