from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import Settings
from .io_utils import slugify


@dataclass(frozen=True)
class AnalysisParameters:
    sample_frames: int = 12
    timeline_scan_points: int = 96
    transcribe_voice: bool = False
    transcription_max_seconds: int = 90
    audio_analysis_max_seconds: int = 120


@dataclass(frozen=True)
class PlanningParameters:
    honor_script_timing: bool = True
    shot_duration_min_s: float = 2.0
    shot_duration_max_s: float = 12.0
    fallback_transition: str = "crossfade"
    include_scene_metadata_in_prompt: bool = True


@dataclass(frozen=True)
class RenderParameters:
    fps: int = 24
    output_width: int | None = None
    output_height: int | None = None


@dataclass(frozen=True)
class GenerationParameters:
    backend: str = "auto"
    use_reference_input: bool = True
    reference_mode: str = "auto"
    reference_asset_limit: int = 4
    video_size: str | None = None
    video_resolution: str | None = "540p"
    video_aspect_ratio: str | None = "9:16"
    video_duration_seconds: int | None = 5
    video_poll_interval_ms: int = 2000
    public_asset_base_url: str | None = None
    kling_generation_mode: str = "multi_image_to_video"
    kling_mode: str | None = None
    kling_sound: bool = False
    kling_local_image_transport: str = "base64"
    kling_model_field: str = "model_name"
    kling_multi_image_min_images: int = 2
    kling_multi_image_max_images: int = 4
    kling_fit_reference_images: bool = True
    kling_cfg_scale: float | None = None
    kling_callback_url: str | None = None
    kling_external_task_id: str | None = None
    kling_camera_control: dict[str, Any] = field(default_factory=dict)
    kling_extra_payload: dict[str, Any] = field(default_factory=dict)
    seed: int | None = None


@dataclass(frozen=True)
class ModelParameters:
    transcription_model: str = "whisper-1"
    style_analysis_model: str = "heuristic_v1"
    video_generation_model: str | None = "kling_2_6_std"
    voice_generation_model: str | None = None


@dataclass(frozen=True)
class SelectionParameters:
    preferred_reference_types: list[str] = field(
        default_factory=lambda: ["reference_videos", "general_asset_videos", "closeup_videos", "broll_videos"]
    )
    max_reference_videos: int | None = None


@dataclass(frozen=True)
class WorkflowParameters:
    save_resolved_run_config: bool = True
    reuse_existing_analysis: bool = False


@dataclass(frozen=True)
class RunParameters:
    run_name: str
    description: str
    input_folder: str
    script_file: str
    output_file: str
    artifact_subdir: str
    voiceover_file: str | None
    analysis_video_subfolders: list[str]
    asset_subfolders: dict[str, str]
    analysis: AnalysisParameters = field(default_factory=AnalysisParameters)
    planning: PlanningParameters = field(default_factory=PlanningParameters)
    render: RenderParameters = field(default_factory=RenderParameters)
    generation: GenerationParameters = field(default_factory=GenerationParameters)
    models: ModelParameters = field(default_factory=ModelParameters)
    selection: SelectionParameters = field(default_factory=SelectionParameters)
    workflow: WorkflowParameters = field(default_factory=WorkflowParameters)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def project_slug(self) -> str:
        return slugify(self.artifact_subdir or self.run_name)

    def input_root(self, settings: Settings) -> Path:
        return settings.video_input_dir / self.input_folder

    def project_dir(self, settings: Settings) -> Path:
        return settings.pipeline_artifacts_dir / self.project_slug

    def script_path(self, settings: Settings) -> Path:
        path = Path(self.script_file).expanduser()
        if path.is_absolute():
            return path
        candidates = [
            self.input_root(settings) / path,
            self.input_root(settings) / "Scripts" / path,
            settings.scripts_dir / path,
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return candidates[1]

    def output_path(self, settings: Settings) -> Path:
        path = Path(self.output_file).expanduser()
        if path.is_absolute():
            return path
        return settings.video_output_dir / path

    def voiceover_path(self, settings: Settings) -> Path | None:
        if not self.voiceover_file:
            return None
        path = Path(self.voiceover_file).expanduser()
        if path.is_absolute():
            return path
        return self.input_root(settings) / path

    def bundle_scan_root(self, settings: Settings) -> Path:
        return self.input_root(settings)

    def supporting_video_sources(self, settings: Settings) -> list[Path]:
        root = self.input_root(settings)
        if self.analysis_video_subfolders:
            relative_paths = self.analysis_video_subfolders
        else:
            relative_paths = [
                self.asset_subfolders[asset_key]
                for asset_key in self.selection.preferred_reference_types
                if asset_key in self.asset_subfolders
            ]

        sources: list[Path] = []
        seen: set[Path] = set()
        for relative_path in relative_paths:
            source = root / relative_path
            if source in seen:
                continue
            seen.add(source)
            sources.append(source)
        return sources

    def analysis_sources(self, settings: Settings) -> list[Path]:
        return self.supporting_video_sources(settings)

    def resolved_asset_paths(self, settings: Settings) -> dict[str, str]:
        root = self.input_root(settings)
        return {
            name: str((root / relative_path).resolve())
            for name, relative_path in self.asset_subfolders.items()
        }


def load_run_parameters(path: Path) -> RunParameters:
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Run parameters file does not exist: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("run_parameters.yaml must contain a YAML object.")

    default_run_name = path.stem
    run_name = _get_text(payload, "run_name", default=default_run_name) or default_run_name
    input_folder = _require_text(payload, "input_folder")

    return RunParameters(
        run_name=run_name,
        description=_get_text(payload, "description", default="") or "",
        input_folder=input_folder,
        script_file=_get_text(payload, "script_file", default="script1.json") or "script1.json",
        output_file=_get_text(payload, "output_file", default=f"{slugify(run_name)}_draft.mp4")
        or f"{slugify(run_name)}_draft.mp4",
        artifact_subdir=_get_text(payload, "artifact_subdir", default=slugify(run_name)) or slugify(run_name),
        voiceover_file=_get_text(payload, "voiceover_file"),
        analysis_video_subfolders=_get_str_list(
            payload,
            "analysis_video_subfolders",
            default=[
                "Supporting Data/general_assets/video",
                "Supporting Data/closeups/videos",
                "Supporting Data/broll/videos",
            ],
        ),
        asset_subfolders=_build_asset_subfolders(payload.get("asset_subfolders")),
        analysis=_build_analysis(payload.get("analysis")),
        planning=_build_planning(payload.get("planning")),
        render=_build_render(payload.get("render")),
        generation=_build_generation(payload.get("generation")),
        models=_build_models(payload.get("models")),
        selection=_build_selection(payload.get("selection")),
        workflow=_build_workflow(payload.get("workflow")),
        metadata={
            key: value
            for key, value in payload.items()
            if key
            not in {
                "run_name",
                "description",
                "input_folder",
                "script_file",
                "output_file",
                "artifact_subdir",
                "voiceover_file",
                "analysis_video_subfolders",
                "asset_subfolders",
                "analysis",
                "planning",
                "render",
                "generation",
                "models",
                "selection",
                "workflow",
            }
        },
    )


def _build_asset_subfolders(payload: Any) -> dict[str, str]:
    defaults = {
        "reference_videos": "Supporting Data/general_assets/video",
        "general_asset_videos": "Supporting Data/general_assets/video",
        "general_asset_images": "Supporting Data/general_assets/images",
        "closeup_videos": "Supporting Data/closeups/videos",
        "closeup_images": "Supporting Data/closeups/images",
        "broll_videos": "Supporting Data/broll/videos",
        "broll_images": "Supporting Data/broll/images",
        "testimonials_videos": "Supporting Data/testimonials/videos",
        "portraits": "Supporting Data/portraits",
        "product_shots": "Supporting Data/product_shots",
        "three_d_models": "Supporting Data/3d_models",
        "style_references": "Supporting Data/style_references",
        "voiceovers": "Supporting Data/audio/voiceovers",
        "music": "Supporting Data/audio/music",
        "sfx": "Supporting Data/audio/sfx",
        "brand_assets": "Supporting Data/brand_assets",
        "logos": "Supporting Data/brand_assets/logos",
        "overlays": "Supporting Data/overlays",
        "documents": "Supporting Data/docs",
        "storyboards": "Supporting Data/docs/storyboards",
        "transcripts": "Supporting Data/docs/transcripts",
    }
    if payload is None:
        return defaults
    if not isinstance(payload, dict):
        raise ValueError("asset_subfolders must be a YAML mapping.")
    merged = defaults.copy()
    for key, value in payload.items():
        if value is None:
            continue
        merged[str(key)] = str(value)
    return merged


def _build_analysis(payload: Any) -> AnalysisParameters:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise ValueError("analysis must be a YAML mapping.")
    return AnalysisParameters(
        sample_frames=_get_int(payload, "sample_frames", default=12),
        timeline_scan_points=_get_int(payload, "timeline_scan_points", default=96),
        transcribe_voice=_get_bool(payload, "transcribe_voice", default=False),
        transcription_max_seconds=_get_int(payload, "transcription_max_seconds", default=90),
        audio_analysis_max_seconds=_get_int(payload, "audio_analysis_max_seconds", default=120),
    )


def _build_planning(payload: Any) -> PlanningParameters:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise ValueError("planning must be a YAML mapping.")
    return PlanningParameters(
        honor_script_timing=_get_bool(payload, "honor_script_timing", default=True),
        shot_duration_min_s=_get_float(payload, "shot_duration_min_s", default=2.0),
        shot_duration_max_s=_get_float(payload, "shot_duration_max_s", default=12.0),
        fallback_transition=_get_text(payload, "fallback_transition", default="crossfade") or "crossfade",
        include_scene_metadata_in_prompt=_get_bool(
            payload,
            "include_scene_metadata_in_prompt",
            default=True,
        ),
    )


def _build_render(payload: Any) -> RenderParameters:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise ValueError("render must be a YAML mapping.")
    return RenderParameters(
        fps=_get_int(payload, "fps", default=24),
        output_width=_get_optional_int(payload, "output_width"),
        output_height=_get_optional_int(payload, "output_height"),
    )


def _build_generation(payload: Any) -> GenerationParameters:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise ValueError("generation must be a YAML mapping.")
    return GenerationParameters(
        backend=_get_text(payload, "backend", default="auto") or "auto",
        use_reference_input=_get_bool(payload, "use_reference_input", default=True),
        reference_mode=_get_text(payload, "reference_mode", default="auto") or "auto",
        reference_asset_limit=_get_int(payload, "reference_asset_limit", default=4),
        video_size=_get_text(payload, "video_size"),
        video_resolution=_get_text(payload, "video_resolution", default="540p"),
        video_aspect_ratio=_get_text(payload, "video_aspect_ratio", default="9:16"),
        video_duration_seconds=_get_optional_int(payload, "video_duration_seconds")
        if "video_duration_seconds" in payload
        else 5,
        video_poll_interval_ms=_get_int(payload, "video_poll_interval_ms", default=2000),
        public_asset_base_url=_get_text(payload, "public_asset_base_url"),
        kling_generation_mode=_get_text(
            payload,
            "kling_generation_mode",
            default="multi_image_to_video",
        )
        or "multi_image_to_video",
        kling_mode=_get_text(payload, "kling_mode"),
        kling_sound=_get_bool(payload, "kling_sound", default=False),
        kling_local_image_transport=_get_text(payload, "kling_local_image_transport", default="base64")
        or "base64",
        kling_model_field=_get_text(payload, "kling_model_field", default="model_name") or "model_name",
        kling_multi_image_min_images=_get_int(payload, "kling_multi_image_min_images", default=2),
        kling_multi_image_max_images=_get_int(payload, "kling_multi_image_max_images", default=4),
        kling_fit_reference_images=_get_bool(payload, "kling_fit_reference_images", default=True),
        kling_cfg_scale=_get_optional_float(payload, "kling_cfg_scale"),
        kling_callback_url=_get_text(payload, "kling_callback_url"),
        kling_external_task_id=_get_text(payload, "kling_external_task_id"),
        kling_camera_control=_get_dict(payload, "kling_camera_control"),
        kling_extra_payload=_get_dict(payload, "kling_extra_payload"),
        seed=_get_optional_int(payload, "seed"),
    )


def _build_models(payload: Any) -> ModelParameters:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise ValueError("models must be a YAML mapping.")
    return ModelParameters(
        transcription_model=_get_text(payload, "transcription_model", default="whisper-1") or "whisper-1",
        style_analysis_model=_get_text(payload, "style_analysis_model", default="heuristic_v1")
        or "heuristic_v1",
        video_generation_model=_get_text(payload, "video_generation_model", default="kling_2_6_std")
        or "kling_2_6_std",
        voice_generation_model=_get_text(payload, "voice_generation_model"),
    )


def _build_selection(payload: Any) -> SelectionParameters:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise ValueError("selection must be a YAML mapping.")
    return SelectionParameters(
        preferred_reference_types=_get_str_list(
            payload,
            "preferred_reference_types",
            default=["reference_videos", "general_asset_videos", "closeup_videos", "broll_videos"],
        ),
        max_reference_videos=_get_optional_int(payload, "max_reference_videos"),
    )


def _build_workflow(payload: Any) -> WorkflowParameters:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise ValueError("workflow must be a YAML mapping.")
    return WorkflowParameters(
        save_resolved_run_config=_get_bool(payload, "save_resolved_run_config", default=True),
        reuse_existing_analysis=_get_bool(payload, "reuse_existing_analysis", default=False),
    )


def _require_text(mapping: dict[str, Any], key: str) -> str:
    value = _get_text(mapping, key)
    if value is None:
        raise ValueError(f"run_parameters.yaml is missing required field: {key}")
    return value


def _get_text(mapping: dict[str, Any], key: str, default: str | None = None) -> str | None:
    value = mapping.get(key)
    if value is None:
        return default
    cleaned = str(value).strip()
    if cleaned == "":
        return default
    return cleaned


def _get_int(mapping: dict[str, Any], key: str, default: int) -> int:
    value = mapping.get(key)
    if value is None:
        return default
    return int(value)


def _get_optional_int(mapping: dict[str, Any], key: str) -> int | None:
    value = mapping.get(key)
    if value in (None, ""):
        return None
    return int(value)


def _get_optional_float(mapping: dict[str, Any], key: str) -> float | None:
    value = mapping.get(key)
    if value in (None, ""):
        return None
    return float(value)


def _get_float(mapping: dict[str, Any], key: str, default: float) -> float:
    value = mapping.get(key)
    if value is None:
        return default
    return float(value)


def _get_bool(mapping: dict[str, Any], key: str, default: bool) -> bool:
    value = mapping.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value for {key}: {value}")


def _get_dict(mapping: dict[str, Any], key: str) -> dict[str, Any]:
    value = mapping.get(key)
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a YAML mapping.")
    return dict(value)


def _get_str_list(mapping: dict[str, Any], key: str, default: list[str] | None = None) -> list[str]:
    value = mapping.get(key)
    if value is None:
        return list(default or [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a YAML list.")
    return [str(item).strip() for item in value if str(item).strip()]
