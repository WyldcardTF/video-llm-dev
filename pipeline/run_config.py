from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import Settings
from .io_utils import slugify


@dataclass(frozen=True)
class AnalysisParameters:
    sample_frames: int = 6
    timeline_scan_points: int = 48
    transcribe_voice: bool = False
    transcription_max_seconds: int = 60
    audio_analysis_max_seconds: int = 90


@dataclass(frozen=True)
class PlanningParameters:
    honor_script_timing: bool = True
    shot_duration_min_s: float = 2.0
    shot_duration_max_s: float = 7.5
    fallback_transition: str = "crossfade"
    include_scene_metadata_in_prompt: bool = True


@dataclass(frozen=True)
class RenderParameters:
    fps: int = 24
    output_width: int | None = None
    output_height: int | None = None


@dataclass(frozen=True)
class ModelParameters:
    transcription_model: str = "whisper-1"
    style_analysis_model: str = "heuristic_v1"
    image_generation_model: str | None = None
    video_generation_model: str | None = None
    voice_generation_model: str | None = None


@dataclass(frozen=True)
class SelectionParameters:
    preferred_reference_types: list[str] = field(
        default_factory=lambda: ["reference_videos", "closeup_videos", "broll_videos"]
    )
    require_videos: bool = True
    allow_images_as_fallback: bool = True
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
        return settings.scripts_dir / path

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

    def required_reference_video_source(self, settings: Settings) -> Path:
        root = self.input_root(settings)
        reference_subfolder = self.asset_subfolders.get("reference_videos", "reference_videos")
        return root / reference_subfolder

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
        script_file=_get_text(payload, "script_file", default="sample1.json") or "sample1.json",
        output_file=_get_text(payload, "output_file", default=f"{slugify(run_name)}_draft.mp4")
        or f"{slugify(run_name)}_draft.mp4",
        artifact_subdir=_get_text(payload, "artifact_subdir", default=slugify(run_name)) or slugify(run_name),
        voiceover_file=_get_text(payload, "voiceover_file"),
        analysis_video_subfolders=_get_str_list(
            payload,
            "analysis_video_subfolders",
            default=["reference_videos", "closeups/videos", "broll/videos"],
        ),
        asset_subfolders=_build_asset_subfolders(payload.get("asset_subfolders")),
        analysis=_build_analysis(payload.get("analysis")),
        planning=_build_planning(payload.get("planning")),
        render=_build_render(payload.get("render")),
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
                "models",
                "selection",
                "workflow",
            }
        },
    )


def _build_asset_subfolders(payload: Any) -> dict[str, str]:
    defaults = {
        "reference_videos": "reference_videos",
        "closeup_videos": "closeups/videos",
        "closeup_images": "closeups/images",
        "broll_videos": "broll/videos",
        "broll_images": "broll/images",
        "portraits": "portraits",
        "product_shots": "product_shots",
        "three_d_models": "3d_models",
        "style_references": "style_references",
        "voiceovers": "audio/voiceovers",
        "music": "audio/music",
        "sfx": "audio/sfx",
        "brand_assets": "brand_assets",
        "logos": "brand_assets/logos",
        "overlays": "overlays",
        "documents": "docs",
        "storyboards": "docs/storyboards",
        "transcripts": "docs/transcripts",
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
        sample_frames=_get_int(payload, "sample_frames", default=6),
        timeline_scan_points=_get_int(payload, "timeline_scan_points", default=48),
        transcribe_voice=_get_bool(payload, "transcribe_voice", default=False),
        transcription_max_seconds=_get_int(payload, "transcription_max_seconds", default=60),
        audio_analysis_max_seconds=_get_int(payload, "audio_analysis_max_seconds", default=90),
    )


def _build_planning(payload: Any) -> PlanningParameters:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise ValueError("planning must be a YAML mapping.")
    return PlanningParameters(
        honor_script_timing=_get_bool(payload, "honor_script_timing", default=True),
        shot_duration_min_s=_get_float(payload, "shot_duration_min_s", default=2.0),
        shot_duration_max_s=_get_float(payload, "shot_duration_max_s", default=7.5),
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


def _build_models(payload: Any) -> ModelParameters:
    payload = payload or {}
    if not isinstance(payload, dict):
        raise ValueError("models must be a YAML mapping.")
    return ModelParameters(
        transcription_model=_get_text(payload, "transcription_model", default="whisper-1") or "whisper-1",
        style_analysis_model=_get_text(payload, "style_analysis_model", default="heuristic_v1")
        or "heuristic_v1",
        image_generation_model=_get_text(payload, "image_generation_model"),
        video_generation_model=_get_text(payload, "video_generation_model"),
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
            default=["reference_videos", "closeup_videos", "broll_videos"],
        ),
        require_videos=_get_bool(payload, "require_videos", default=True),
        allow_images_as_fallback=_get_bool(payload, "allow_images_as_fallback", default=True),
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


def _get_str_list(mapping: dict[str, Any], key: str, default: list[str] | None = None) -> list[str]:
    value = mapping.get(key)
    if value is None:
        return list(default or [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a YAML list.")
    return [str(item).strip() for item in value if str(item).strip()]
