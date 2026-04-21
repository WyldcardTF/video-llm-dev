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
    "sora_2": VideoModelPreset(
        preset_id="sora_2",
        provider="openai_video",
        model="sora-2",
        label="Sora 2",
        price_tier="medium",
        quality_tier="frontier",
        default_size="720x1280",
        default_aspect_ratio="9:16",
        default_duration_seconds=4,
        reference_asset_limit=1,
        notes="Strong default when you want OpenAI quality without Pro pricing.",
    ),
    "sora_2_pro": VideoModelPreset(
        preset_id="sora_2_pro",
        provider="openai_video",
        model="sora-2-pro",
        label="Sora 2 Pro",
        price_tier="high",
        quality_tier="best",
        default_size="1080x1920",
        default_aspect_ratio="9:16",
        default_duration_seconds=8,
        reference_asset_limit=1,
        notes="Use for final-quality passes, not cheap prompt exploration.",
    ),
    "veo_3_1_lite": VideoModelPreset(
        preset_id="veo_3_1_lite",
        provider="google_veo",
        model="veo-3.1-lite-generate-001",
        label="Google Veo 3.1 Lite",
        price_tier="low",
        quality_tier="draft",
        default_aspect_ratio="9:16",
        default_resolution="720p",
        default_duration_seconds=4,
        reference_asset_limit=0,
        notes="Cheap Google Veo option for prompt and timing tests; treat references as prompt guidance.",
    ),
    "veo_3_1_fast": VideoModelPreset(
        preset_id="veo_3_1_fast",
        provider="google_veo",
        model="veo-3.1-fast-generate-001",
        label="Google Veo 3.1 Fast",
        price_tier="medium",
        quality_tier="fast",
        default_aspect_ratio="9:16",
        default_resolution="720p",
        default_duration_seconds=4,
        reference_asset_limit=3,
        notes="Good middle ground for fast Veo tests with asset reference images.",
    ),
    "veo_3_1_quality": VideoModelPreset(
        preset_id="veo_3_1_quality",
        provider="google_veo",
        model="veo-3.1-generate-001",
        label="Google Veo 3.1",
        price_tier="high",
        quality_tier="production",
        default_aspect_ratio="9:16",
        default_resolution="1080p",
        default_duration_seconds=8,
        reference_asset_limit=3,
        notes="Higher-quality Veo pass for promising scenes.",
    ),
    "kling_2_6_std": VideoModelPreset(
        preset_id="kling_2_6_std",
        provider="kling",
        model="kling-v2.6",
        label="Kling 2.6 Multi-Image Standard",
        price_tier="low",
        quality_tier="draft",
        default_aspect_ratio="9:16",
        default_resolution="540p",
        default_duration_seconds=5,
        kling_mode="standard",
        kling_sound=False,
        reference_asset_limit=4,
        notes="Lowest-friction multi-image-to-video preset: silent, short, and low-resolution for early iteration.",
    ),
    "kling_2_6_pro": VideoModelPreset(
        preset_id="kling_2_6_pro",
        provider="kling",
        model="kling-v2.6",
        label="Kling 2.6 Multi-Image Pro",
        price_tier="medium",
        quality_tier="production",
        default_aspect_ratio="9:16",
        default_resolution="720p",
        default_duration_seconds=5,
        kling_mode="professional",
        kling_sound=False,
        reference_asset_limit=4,
        notes="Higher-quality Kling multi-image pass while staying below frontier-model cost.",
    ),
    "kling_2_6_pro_audio": VideoModelPreset(
        preset_id="kling_2_6_pro_audio",
        provider="kling",
        model="kling-v2.6-pro",
        label="Kling 2.6 Pro With Audio",
        price_tier="medium-high",
        quality_tier="production",
        default_aspect_ratio="9:16",
        default_resolution="720p",
        default_duration_seconds=5,
        kling_mode="professional",
        kling_sound=True,
        reference_asset_limit=4,
        notes="Kling 2.6 with native audio enabled; useful when sound is part of the generated shot.",
    ),
    "kling_2_5_turbo": VideoModelPreset(
        preset_id="kling_2_5_turbo",
        provider="kling",
        model="kling-v2.5-turbo",
        label="Kling 2.5 Turbo",
        price_tier="lowest",
        quality_tier="rough-draft",
        default_aspect_ratio="9:16",
        default_duration_seconds=5,
        kling_mode="standard",
        kling_sound=False,
        reference_asset_limit=1,
        notes="Fastest cheap scratchpad option if your Kling account exposes it.",
    ),
}


BACKEND_ALIASES = {
    "auto": "auto",
    "openai": "openai_video",
    "openai_video": "openai_video",
    "openai_videos": "openai_video",
    "sora": "openai_video",
    "google": "google_veo",
    "google_veo": "google_veo",
    "veo": "google_veo",
    "vertex_veo": "google_veo",
    "kling": "kling",
    "kling_api": "kling",
}


def resolve_video_model_selection(run_parameters: RunParameters) -> VideoModelSelection:
    requested_model = (run_parameters.models.video_generation_model or "kling_2_6_std").strip()
    preset = VIDEO_MODEL_PRESETS.get(requested_model)
    raw_backend = (run_parameters.generation.backend or "auto").strip().lower()
    backend = BACKEND_ALIASES.get(raw_backend, raw_backend)

    if preset is not None:
        provider = preset.provider if backend == "auto" else backend
        return VideoModelSelection(
            provider=provider,
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

    inferred_provider = _infer_provider_from_model(requested_model)
    provider = inferred_provider if backend == "auto" else backend
    return VideoModelSelection(
        provider=provider,
        model=requested_model,
        preset_id=None,
        label=requested_model,
        price_tier="custom",
        quality_tier="custom",
        default_aspect_ratio=run_parameters.generation.video_aspect_ratio,
        default_resolution=run_parameters.generation.video_resolution,
        reference_asset_limit=run_parameters.generation.reference_asset_limit,
        notes="Custom model ID. Backend was inferred from the model name unless explicitly configured.",
    )


def list_video_model_presets() -> list[VideoModelPreset]:
    return list(VIDEO_MODEL_PRESETS.values())


def _infer_provider_from_model(model: str) -> str:
    lowered = model.strip().lower()
    if lowered.startswith("sora"):
        return "openai_video"
    if lowered.startswith("veo"):
        return "google_veo"
    if lowered.startswith("kling"):
        return "kling"
    return "openai_video"
