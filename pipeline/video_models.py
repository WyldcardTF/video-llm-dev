from __future__ import annotations

from dataclasses import dataclass

from .run_config import RunParameters


@dataclass(frozen=True)
class VideoModelPreset:
    preset_id: str
    provider: str
    model: str
    label: str
    price_tier: str
    quality_tier: str
    default_size: str | None = None
    default_aspect_ratio: str | None = None
    default_resolution: str | None = None
    default_duration_seconds: int | None = None
    kling_mode: str | None = None
    kling_sound: bool = False
    reference_asset_limit: int = 1
    notes: str = ""


@dataclass(frozen=True)
class VideoModelSelection:
    provider: str
    model: str
    preset_id: str | None
    label: str
    price_tier: str
    quality_tier: str
    default_size: str | None = None
    default_aspect_ratio: str | None = None
    default_resolution: str | None = None
    default_duration_seconds: int | None = None
    kling_mode: str | None = None
    kling_sound: bool = False
    reference_asset_limit: int = 1
    notes: str = ""


VIDEO_MODEL_PRESETS: dict[str, VideoModelPreset] = {
    "kling_2_6_std": VideoModelPreset(
        preset_id="kling_2_6_std",
        provider="kling",
        model="kling-v2-6",
        label="Kling 2.6 Multi-Image Standard",
        price_tier="low",
        quality_tier="draft",
        default_aspect_ratio="9:16",
        default_resolution="540p",
        default_duration_seconds=5,
        kling_mode="std",
        kling_sound=False,
        reference_asset_limit=4,
        notes="Cheap Kling multi-image preset: silent, short, and low-resolution for early iteration.",
    ),
    "kling_2_6_pro": VideoModelPreset(
        preset_id="kling_2_6_pro",
        provider="kling",
        model="kling-v2-6",
        label="Kling 2.6 Multi-Image Pro",
        price_tier="medium",
        quality_tier="production",
        default_aspect_ratio="9:16",
        default_resolution="720p",
        default_duration_seconds=5,
        kling_mode="pro",
        kling_sound=False,
        reference_asset_limit=4,
        notes="Higher-quality Kling pass after the prompt and references look right.",
    ),
    "kling_2_6_pro_audio": VideoModelPreset(
        preset_id="kling_2_6_pro_audio",
        provider="kling",
        model="kling-v2-6",
        label="Kling 2.6 Pro With Audio",
        price_tier="medium-high",
        quality_tier="production",
        default_aspect_ratio="9:16",
        default_resolution="720p",
        default_duration_seconds=5,
        kling_mode="pro",
        kling_sound=True,
        reference_asset_limit=4,
        notes="Kling 2.6 with native audio enabled when generated sound is needed.",
    ),
    "kling_2_5_turbo": VideoModelPreset(
        preset_id="kling_2_5_turbo",
        provider="kling",
        model="kling-v2-5-turbo",
        label="Kling 2.5 Turbo",
        price_tier="lowest",
        quality_tier="rough-draft",
        default_aspect_ratio="9:16",
        default_duration_seconds=5,
        kling_mode="std",
        kling_sound=False,
        reference_asset_limit=1,
        notes="Fast cheap scratchpad option if your Kling account exposes it.",
    ),
}


BACKEND_ALIASES = {
    "auto": "auto",
    "kling": "kling",
    "kling_api": "kling",
}


def resolve_video_model_selection(run_parameters: RunParameters) -> VideoModelSelection:
    requested_model = (run_parameters.models.video_generation_model or "kling_2_6_std").strip()
    preset = VIDEO_MODEL_PRESETS.get(requested_model)
    raw_backend = (run_parameters.generation.backend or "auto").strip().lower()
    backend = BACKEND_ALIASES.get(raw_backend, raw_backend)
    if backend not in {"auto", "kling"}:
        raise ValueError("Only the Kling video generation backend is supported.")

    if preset is not None:
        return VideoModelSelection(
            provider="kling",
            model=preset.model,
            preset_id=preset.preset_id,
            label=preset.label,
            price_tier=preset.price_tier,
            quality_tier=preset.quality_tier,
            default_size=preset.default_size,
            default_aspect_ratio=preset.default_aspect_ratio,
            default_resolution=preset.default_resolution,
            default_duration_seconds=preset.default_duration_seconds,
            kling_mode=preset.kling_mode,
            kling_sound=preset.kling_sound,
            reference_asset_limit=preset.reference_asset_limit,
            notes=preset.notes,
        )

    if not requested_model.lower().startswith("kling"):
        raise ValueError("Only Kling model ids are supported. Use a kling_* preset or raw Kling model id.")
    return VideoModelSelection(
        provider="kling",
        model=requested_model,
        preset_id=None,
        label=requested_model,
        price_tier="custom",
        quality_tier="custom",
        default_aspect_ratio=run_parameters.generation.video_aspect_ratio,
        default_resolution=run_parameters.generation.video_resolution,
        reference_asset_limit=run_parameters.generation.reference_asset_limit,
        notes="Custom Kling model id.",
    )


def list_video_model_presets() -> list[VideoModelPreset]:
    return list(VIDEO_MODEL_PRESETS.values())
