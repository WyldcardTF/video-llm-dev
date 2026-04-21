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
    generated_assets_dir_name: str
    video_analyses_filename: str
    style_profile_filename: str
    asset_inventory_filename: str
    generated_assets_manifest_filename: str
    shot_plan_filename: str
    continuity_profile_filename: str
    resolved_run_config_filename: str
    openai_api_key: str | None
    google_vertex_project: str | None
    google_vertex_location: str
    google_vertex_access_token: str | None
    kling_api_access_key: str | None
    kling_api_secret_key: str | None
    kling_base_url: str
    kling_multi_image_endpoint: str
    kling_image_endpoint: str
    kling_text_endpoint: str
    kling_status_endpoint_template: str

    def analyses_path(self, project_dir: Path) -> Path:
        return project_dir / self.video_analyses_filename

    def style_profile_path(self, project_dir: Path) -> Path:
        return project_dir / self.style_profile_filename

    def asset_inventory_path(self, project_dir: Path) -> Path:
        return project_dir / self.asset_inventory_filename

    def generated_assets_dir(self, project_dir: Path) -> Path:
        return project_dir / self.generated_assets_dir_name

    def generated_assets_manifest_path(self, project_dir: Path) -> Path:
        return project_dir / self.generated_assets_manifest_filename

    def shot_plan_path(self, project_dir: Path) -> Path:
        return project_dir / self.shot_plan_filename

    def continuity_profile_path(self, project_dir: Path) -> Path:
        return project_dir / self.continuity_profile_filename

    def resolved_run_config_path(self, project_dir: Path) -> Path:
        return project_dir / self.resolved_run_config_filename


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_environment()

    app_base_dir = _as_path(_env_text("APP_BASE_DIR", "/app") or "/app", Path.cwd())
    scripts_dir = _env_path("SCRIPTS_DIR", "Input", app_base_dir)
    video_input_dir = _env_path("VIDEO_INPUT_DIR", "Input", app_base_dir)
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
        generated_assets_dir_name=_env_text("GENERATED_ASSETS_DIR_NAME", "generated_assets")
        or "generated_assets",
        video_analyses_filename=_env_text("VIDEO_ANALYSES_FILENAME", "video_analyses.json")
        or "video_analyses.json",
        style_profile_filename=_env_text("STYLE_PROFILE_FILENAME", "style_profile.json")
        or "style_profile.json",
        asset_inventory_filename=_env_text("ASSET_INVENTORY_FILENAME", "asset_inventory.json")
        or "asset_inventory.json",
        generated_assets_manifest_filename=_env_text(
            "GENERATED_ASSETS_MANIFEST_FILENAME",
            "generated_assets.json",
        )
        or "generated_assets.json",
        shot_plan_filename=_env_text("SHOT_PLAN_FILENAME", "shot_plan.json") or "shot_plan.json",
        continuity_profile_filename=_env_text("CONTINUITY_PROFILE_FILENAME", "continuity_profile.json")
        or "continuity_profile.json",
        resolved_run_config_filename=_env_text("RESOLVED_RUN_CONFIG_FILENAME", "resolved_run_config.json")
        or "resolved_run_config.json",
        openai_api_key=_env_text("OPENAI_API_KEY"),
        google_vertex_project=_env_text("GOOGLE_VERTEX_PROJECT"),
        google_vertex_location=_env_text("GOOGLE_VERTEX_LOCATION", "us-central1") or "us-central1",
        google_vertex_access_token=_env_text("GOOGLE_VERTEX_ACCESS_TOKEN"),
        kling_api_access_key=_env_text("KLING_API_ACCESS_KEY"),
        kling_api_secret_key=_env_text("KLING_API_SECRET_KEY"),
        kling_base_url=_env_text("KLING_BASE_URL", "https://api.klingapi.com") or "https://api.klingapi.com",
        kling_multi_image_endpoint=_env_text(
            "KLING_MULTI_IMAGE_ENDPOINT",
            "/v1/videos/multi-image2video",
        )
        or "/v1/videos/multi-image2video",
        kling_image_endpoint=_env_text("KLING_IMAGE_ENDPOINT", "/v1/videos/image2video")
        or "/v1/videos/image2video",
        kling_text_endpoint=_env_text("KLING_TEXT_ENDPOINT", "/v1/videos/text2video")
        or "/v1/videos/text2video",
        kling_status_endpoint_template=_env_text(
            "KLING_STATUS_ENDPOINT_TEMPLATE",
            "{endpoint}/{task_id}",
        )
        or "{endpoint}/{task_id}",
    )
