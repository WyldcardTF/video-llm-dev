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


@dataclass(frozen=True)
class Settings:
    app_base_dir: Path
    scripts_dir: Path
    video_input_dir: Path
    video_output_dir: Path
    pipeline_artifacts_dir: Path
    frames_dir_name: str
    audio_dir_name: str
    video_analyses_filename: str
    style_profile_filename: str
    shot_plan_filename: str
    resolved_run_config_filename: str
    openai_api_key: str | None

    def analyses_path(self, project_dir: Path) -> Path:
        return project_dir / self.video_analyses_filename

    def style_profile_path(self, project_dir: Path) -> Path:
        return project_dir / self.style_profile_filename

    def shot_plan_path(self, project_dir: Path) -> Path:
        return project_dir / self.shot_plan_filename

    def resolved_run_config_path(self, project_dir: Path) -> Path:
        return project_dir / self.resolved_run_config_filename


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_environment()

    app_base_dir = _as_path(_env_text("APP_BASE_DIR", "/app") or "/app", Path.cwd())
    scripts_dir = _env_path("SCRIPTS_DIR", "Scripts", app_base_dir)
    video_input_dir = _env_path("VIDEO_INPUT_DIR", "Video Input", app_base_dir)
    video_output_dir = _env_path("VIDEO_OUTPUT_DIR", "Video Output", app_base_dir)
    pipeline_artifacts_dir = _env_path(
        "PIPELINE_ARTIFACTS_DIR",
        _env_text("PIPELINE_PROJECT_DIR", "artifacts"),
        app_base_dir,
    )

    return Settings(
        app_base_dir=app_base_dir,
        scripts_dir=scripts_dir,
        video_input_dir=video_input_dir,
        video_output_dir=video_output_dir,
        pipeline_artifacts_dir=pipeline_artifacts_dir,
        frames_dir_name=_env_text("FRAMES_DIR_NAME", "frames") or "frames",
        audio_dir_name=_env_text("AUDIO_DIR_NAME", "audio") or "audio",
        video_analyses_filename=_env_text("VIDEO_ANALYSES_FILENAME", "video_analyses.json")
        or "video_analyses.json",
        style_profile_filename=_env_text("STYLE_PROFILE_FILENAME", "style_profile.json")
        or "style_profile.json",
        shot_plan_filename=_env_text("SHOT_PLAN_FILENAME", "shot_plan.json") or "shot_plan.json",
        resolved_run_config_filename=_env_text("RESOLVED_RUN_CONFIG_FILENAME", "resolved_run_config.json")
        or "resolved_run_config.json",
        openai_api_key=_env_text("OPENAI_API_KEY"),
    )
