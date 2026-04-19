from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv


def _load_environment() -> None:
    dotenv_path = os.getenv("DOTENV_PATH", ".env")
    load_dotenv(dotenv_path=dotenv_path, override=False)


def _env_text(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        return default
    cleaned = value.strip()
    if cleaned == "":
        return default
    return cleaned


def _env_int(name: str, default: int) -> int:
    value = _env_text(name)
    if value is None:
        return default
    return int(value)


def _env_bool(name: str, default: bool) -> bool:
    value = _env_text(name)
    if value is None:
        return default

    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value for {name}: {value}")


def _as_path(value: str | Path, base_dir: Path) -> Path:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    return candidate


def _env_path(name: str, default: str | Path, base_dir: Path) -> Path:
    value = _env_text(name)
    if value is None:
        return _as_path(default, base_dir)
    return _as_path(value, base_dir)


def _env_optional_path(name: str, base_dir: Path) -> Path | None:
    value = _env_text(name)
    if value is None:
        return None
    return _as_path(value, base_dir)


@dataclass(frozen=True)
class Settings:
    app_base_dir: Path
    video_input_dir: Path
    video_output_dir: Path
    pipeline_project_dir: Path
    pipeline_source_path: Path | None
    script_input_file: Path
    voiceover_input_file: Path | None
    output_filename: str
    video_analyses_filename: str
    style_profile_filename: str
    shot_plan_filename: str
    frames_dir_name: str
    audio_dir_name: str
    sample_frames: int
    timeline_scan_points: int
    transcribe_voice: bool
    transcription_max_seconds: int
    audio_analysis_max_seconds: int
    render_fps: int
    openai_api_key: str | None
    openai_transcribe_model: str

    def default_source(self) -> Path:
        return self.pipeline_source_path or self.video_input_dir

    def default_output_path(self) -> Path:
        return self.video_output_dir / self.output_filename

    def analyses_path(self, project_dir: Path | None = None) -> Path:
        base = project_dir or self.pipeline_project_dir
        return base / self.video_analyses_filename

    def style_profile_path(self, project_dir: Path | None = None) -> Path:
        base = project_dir or self.pipeline_project_dir
        return base / self.style_profile_filename

    def shot_plan_path(self, project_dir: Path | None = None) -> Path:
        base = project_dir or self.pipeline_project_dir
        return base / self.shot_plan_filename


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_environment()

    app_base_dir = _as_path(_env_text("APP_BASE_DIR", "/app") or "/app", Path.cwd())
    video_input_dir = _env_path("VIDEO_INPUT_DIR", "Video Input", app_base_dir)
    video_output_dir = _env_path("VIDEO_OUTPUT_DIR", "Video Output", app_base_dir)
    pipeline_project_dir = _env_path("PIPELINE_PROJECT_DIR", "artifacts/session", app_base_dir)

    return Settings(
        app_base_dir=app_base_dir,
        video_input_dir=video_input_dir,
        video_output_dir=video_output_dir,
        pipeline_project_dir=pipeline_project_dir,
        pipeline_source_path=_env_optional_path("PIPELINE_SOURCE_PATH", app_base_dir),
        script_input_file=_env_path("SCRIPT_INPUT_FILE", video_input_dir / "script.txt", app_base_dir),
        voiceover_input_file=_env_optional_path("VOICEOVER_INPUT_FILE", app_base_dir),
        output_filename=_env_text("OUTPUT_FILENAME", "draft.mp4") or "draft.mp4",
        video_analyses_filename=_env_text("VIDEO_ANALYSES_FILENAME", "video_analyses.json") or "video_analyses.json",
        style_profile_filename=_env_text("STYLE_PROFILE_FILENAME", "style_profile.json") or "style_profile.json",
        shot_plan_filename=_env_text("SHOT_PLAN_FILENAME", "shot_plan.json") or "shot_plan.json",
        frames_dir_name=_env_text("FRAMES_DIR_NAME", "frames") or "frames",
        audio_dir_name=_env_text("AUDIO_DIR_NAME", "audio") or "audio",
        sample_frames=_env_int("SAMPLE_FRAMES", 6),
        timeline_scan_points=_env_int("TIMELINE_SCAN_POINTS", 48),
        transcribe_voice=_env_bool("TRANSCRIBE_VOICE", False),
        transcription_max_seconds=_env_int("TRANSCRIPTION_MAX_SECONDS", 60),
        audio_analysis_max_seconds=_env_int("AUDIO_ANALYSIS_MAX_SECONDS", 90),
        render_fps=_env_int("RENDER_FPS", 24),
        openai_api_key=_env_text("OPENAI_API_KEY"),
        openai_transcribe_model=_env_text("OPENAI_TRANSCRIBE_MODEL", "whisper-1") or "whisper-1",
    )
