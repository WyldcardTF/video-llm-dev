from __future__ import annotations

import base64
import subprocess
from dataclasses import replace
from pathlib import Path

import cv2

from .config import Settings
from .ingest import VIDEO_EXTENSIONS
from .io_utils import ensure_dir
from .models import GeneratedAssetManifest, GeneratedAssetRecord, GenerationPlan, ShotPlanItem, StyleProfile
from .run_config import RunParameters


def resolve_generation_backend(run_parameters: RunParameters) -> str:
    raw_backend = run_parameters.generation.backend.strip().lower()
    aliases = {
        "draft": "draft_compositor",
        "draft_compositor": "draft_compositor",
        "openai_image": "openai_image",
        "openai_images": "openai_image",
        "openai_video": "openai_video",
        "openai_videos": "openai_video",
    }
    if raw_backend == "auto":
        if run_parameters.models.video_generation_model:
            return "openai_video"
        if run_parameters.models.image_generation_model:
            return "openai_image"
        return "draft_compositor"
    return aliases.get(raw_backend, raw_backend or "draft_compositor")


def generate_assets_for_plan(
    plan: GenerationPlan,
    style_profile: StyleProfile,
    run_parameters: RunParameters,
    settings: Settings,
    project_dir: Path,
) -> tuple[GenerationPlan, GeneratedAssetManifest]:
    backend = resolve_generation_backend(run_parameters)
    output_dir = ensure_dir(settings.generated_assets_dir(project_dir))
    manifest = GeneratedAssetManifest(
        backend=backend,
        output_dir=str(output_dir),
    )

    if backend == "draft_compositor":
        return replace(plan, generation_backend=backend), manifest

    if backend not in {"openai_image", "openai_video"}:
        raise ValueError(
            "Unsupported generation backend "
            f"'{backend}'. Expected one of: draft_compositor, auto, openai_image, openai_video."
        )

    if not settings.openai_api_key:
        raise RuntimeError(
            "An OpenAI API key is required for generated assets. "
            "Set OPENAI_API_KEY in .env or choose generation.backend: draft_compositor."
        )

    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    updated_items: list[ShotPlanItem] = []

    for item in plan.items:
        try:
            if backend == "openai_video":
                updated_item, record = _generate_video_asset(
                    client=client,
                    item=item,
                    style_profile=style_profile,
                    run_parameters=run_parameters,
                    output_dir=output_dir,
                )
            else:
                updated_item, record = _generate_image_asset(
                    client=client,
                    item=item,
                    style_profile=style_profile,
                    run_parameters=run_parameters,
                    output_dir=output_dir,
                )
        except Exception as exc:
            if not run_parameters.generation.allow_fallback_to_draft:
                raise
            updated_item = item
            record = GeneratedAssetRecord(
                shot_index=item.index,
                backend=backend,
                media_kind=item.media_kind,
                status="fallback",
                source_asset_path=item.source_asset_path,
                prompt=_build_backend_prompt(item),
                error=str(exc),
            )

        updated_items.append(updated_item)
        manifest.items.append(record)

    return replace(plan, items=updated_items, generation_backend=backend), manifest


def _generate_image_asset(
    client: object,
    item: ShotPlanItem,
    style_profile: StyleProfile,
    run_parameters: RunParameters,
    output_dir: Path,
) -> tuple[ShotPlanItem, GeneratedAssetRecord]:
    model_name = run_parameters.models.image_generation_model or "gpt-image-1"
    prompt = _build_backend_prompt(item)
    output_path = output_dir / f"shot_{item.index:03d}.png"
    reference_path = _prepare_image_reference(item, output_dir)
    size = run_parameters.generation.image_size or _derive_image_size(style_profile)
    quality = run_parameters.generation.image_quality

    if reference_path and run_parameters.generation.use_reference_input:
        response = client.images.edit(
            model=model_name,
            image=reference_path,
            prompt=prompt,
            quality=quality,
            size=size,
            output_format="png",
        )
    else:
        response = client.images.generate(
            model=model_name,
            prompt=prompt,
            quality=quality,
            size=size,
            output_format="png",
        )

    images = getattr(response, "data", None) or []
    if not images:
        raise RuntimeError("The image generation backend returned no images.")

    image_payload = images[0]
    encoded = getattr(image_payload, "b64_json", None)
    if not encoded:
        raise RuntimeError("The image generation backend did not return base64 image content.")

    output_path.write_bytes(base64.b64decode(encoded))
    revised_prompt = getattr(image_payload, "revised_prompt", None)

    updated_item = replace(
        item,
        reference_image=str(output_path),
        source_asset_path=str(output_path),
        source_asset_type="generated_image",
        media_kind="image",
        clip_start_s=None,
        clip_duration_s=None,
        motion_strategy="generated_image",
    )
    record = GeneratedAssetRecord(
        shot_index=item.index,
        backend="openai_image",
        media_kind="image",
        status="generated",
        asset_path=str(output_path),
        model=model_name,
        source_asset_path=item.source_asset_path,
        prompt=prompt,
        revised_prompt=revised_prompt,
    )
    return updated_item, record


def _generate_video_asset(
    client: object,
    item: ShotPlanItem,
    style_profile: StyleProfile,
    run_parameters: RunParameters,
    output_dir: Path,
) -> tuple[ShotPlanItem, GeneratedAssetRecord]:
    model_name = run_parameters.models.video_generation_model or "sora-2"
    prompt = _build_backend_prompt(item)
    output_path = output_dir / f"shot_{item.index:03d}.mp4"
    size = run_parameters.generation.video_size or _derive_video_size(style_profile)
    seconds = _derive_video_seconds(item.duration_s)
    input_reference = None
    if run_parameters.generation.use_reference_input:
        input_reference = _prepare_video_reference(item, output_dir, seconds=seconds)

    request_kwargs = {
        "model": model_name,
        "prompt": prompt,
        "seconds": seconds,
        "size": size,
        "poll_interval_ms": run_parameters.generation.video_poll_interval_ms,
    }
    if input_reference is not None:
        request_kwargs["input_reference"] = input_reference

    video = client.videos.create_and_poll(**request_kwargs)
    status = getattr(video, "status", None)
    if status != "completed":
        error = getattr(video, "error", None)
        raise RuntimeError(f"Video generation failed with status={status} error={error}")

    content = client.videos.download_content(video.id, variant="video")
    output_path.write_bytes(content.content)

    updated_item = replace(
        item,
        source_asset_path=str(output_path),
        source_asset_type="generated_video",
        media_kind="video",
        clip_start_s=0.0,
        clip_duration_s=min(float(seconds), item.duration_s),
        motion_strategy="generated_video",
    )
    record = GeneratedAssetRecord(
        shot_index=item.index,
        backend="openai_video",
        media_kind="video",
        status="generated",
        asset_path=str(output_path),
        model=model_name,
        source_asset_path=item.source_asset_path,
        prompt=prompt,
        remote_id=getattr(video, "id", None),
    )
    return updated_item, record


def _build_backend_prompt(item: ShotPlanItem) -> str:
    positive = item.generation_prompt or item.visual_direction or item.narration
    negative = item.negative_prompt or ""
    prompt = positive.strip()
    if negative:
        prompt += f" Avoid: {negative.strip()}"
    return prompt.strip()


def _prepare_image_reference(item: ShotPlanItem, output_dir: Path) -> Path | None:
    candidates = [
        item.reference_image,
        item.source_asset_path,
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser().resolve()
        if not path.exists():
            continue
        if path.suffix.lower() in VIDEO_EXTENSIONS:
            extracted_path = output_dir / f"shot_{item.index:03d}_reference.png"
            return _extract_video_frame(path, extracted_path, item.clip_start_s or 0.0)
        return path
    return None


def _prepare_video_reference(item: ShotPlanItem, output_dir: Path, seconds: int) -> Path | None:
    source_path = item.source_asset_path or item.reference_image
    if not source_path:
        return None

    path = Path(source_path).expanduser().resolve()
    if not path.exists():
        return None
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        return path

    clip_path = output_dir / f"shot_{item.index:03d}_reference.mp4"
    clip_duration = min(item.clip_duration_s or item.duration_s, float(seconds))
    clip_duration = max(clip_duration, 1.0)
    start_s = max(item.clip_start_s or 0.0, 0.0)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        str(start_s),
        "-i",
        str(path),
        "-t",
        str(clip_duration),
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(clip_path),
    ]
    process = subprocess.run(command, capture_output=True, check=False)
    if process.returncode != 0 or not clip_path.exists():
        return path
    return clip_path


def _extract_video_frame(source_path: Path, output_path: Path, timestamp_s: float) -> Path | None:
    capture = cv2.VideoCapture(str(source_path))
    if not capture.isOpened():
        return None
    fps = capture.get(cv2.CAP_PROP_FPS) or 24.0
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    frame_index = min(int(round(max(timestamp_s, 0.0) * fps)), max(frame_count - 1, 0))
    capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    success, frame = capture.read()
    capture.release()
    if not success or frame is None:
        return None
    cv2.imwrite(str(output_path), frame)
    return output_path


def _derive_image_size(style_profile: StyleProfile) -> str:
    width = style_profile.target_width
    height = style_profile.target_height
    if height > width:
        return "1024x1536"
    if width > height:
        return "1536x1024"
    return "1024x1024"


def _derive_video_size(style_profile: StyleProfile) -> str:
    width = style_profile.target_width
    height = style_profile.target_height
    if height > width:
        return "720x1280"
    return "1280x720"


def _derive_video_seconds(duration_s: float) -> int:
    if duration_s <= 4.0:
        return 4
    if duration_s <= 8.0:
        return 8
    return 12
