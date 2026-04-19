from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import cli
from pipeline.config import Settings
from pipeline.io_utils import read_json, write_json
from pipeline.models import AssetInventory, GeneratedAssetManifest, GeneratedAssetRecord, StyleProfile
from pipeline.run_config import RunParameters


class CliWorkflowTests(unittest.TestCase):
    def test_generate_requires_existing_training_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            test_settings = _build_settings(temp_root)
            run_parameters = _build_run_parameters()
            _write_run_config(temp_root, run_parameters)

            with patch.object(cli, "settings", test_settings):
                with self.assertRaises(FileNotFoundError) as exc_info:
                    cli.generate(
                        run_config=temp_root / "run_parameters.yaml",
                        script_file=None,
                        output=None,
                        project_dir=None,
                    )

            self.assertIn("No trained style profile was found", str(exc_info.exception))
            self.assertIn("python -m pipeline train", str(exc_info.exception))

    def test_generate_uses_trained_style_profile_without_retraining(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            test_settings = _build_settings(temp_root)
            run_parameters = _build_run_parameters()
            _write_run_config(temp_root, run_parameters)
            _write_script_file(temp_root)

            project_dir = test_settings.pipeline_artifacts_dir / run_parameters.artifact_subdir
            project_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                test_settings.style_profile_path(project_dir),
                StyleProfile(
                    source_videos=["/tmp/reference.mp4"],
                    target_width=1280,
                    target_height=720,
                    pacing_label="medium",
                    preferred_shot_duration_s=4.0,
                    average_brightness=0.5,
                    average_motion=0.1,
                    color_palette=["#101010", "#E0E0E0"],
                    voice_style="balanced voice",
                    style_summary="test summary",
                    reference_images=[],
                ),
            )
            write_json(
                test_settings.asset_inventory_path(project_dir),
                AssetInventory(
                    items=[],
                    summary={},
                ),
            )

            with patch.object(cli, "settings", test_settings):
                with patch("pipeline.cli._resolve_video_paths", side_effect=AssertionError("should not retrain")):
                    with patch("pipeline.cli.render_plan", return_value=test_settings.video_output_dir / "sample.mp4"):
                        cli.generate(
                            run_config=temp_root / "run_parameters.yaml",
                            script_file=None,
                            output=None,
                            project_dir=None,
                        )

            shot_plan = read_json(test_settings.shot_plan_path(project_dir))
            self.assertEqual(len(shot_plan["items"]), 1)
            self.assertEqual(shot_plan["items"][0]["title"], "Scene 1")
            generated_assets = read_json(test_settings.generated_assets_manifest_path(project_dir))
            self.assertEqual(generated_assets["backend"], "draft_compositor")
            self.assertEqual(generated_assets["items"], [])

    def test_generate_writes_generated_assets_manifest_when_backend_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            test_settings = _build_settings(temp_root)
            run_parameters = _build_run_parameters()
            _write_run_config(
                temp_root,
                run_parameters,
                extra_payload={
                    "generation": {
                        "backend": "openai_image",
                    },
                    "models": {
                        "image_generation_model": "gpt-image-1",
                    },
                },
            )
            _write_script_file(temp_root)

            project_dir = test_settings.pipeline_artifacts_dir / run_parameters.artifact_subdir
            project_dir.mkdir(parents=True, exist_ok=True)
            write_json(
                test_settings.style_profile_path(project_dir),
                StyleProfile(
                    source_videos=["/tmp/reference.mp4"],
                    target_width=1280,
                    target_height=720,
                    pacing_label="medium",
                    preferred_shot_duration_s=4.0,
                    average_brightness=0.5,
                    average_motion=0.1,
                    color_palette=["#101010", "#E0E0E0"],
                    voice_style="balanced voice",
                    style_summary="test summary",
                    reference_images=[],
                ),
            )
            write_json(
                test_settings.asset_inventory_path(project_dir),
                AssetInventory(
                    items=[],
                    summary={},
                ),
            )

            generated_manifest = GeneratedAssetManifest(
                backend="openai_image",
                output_dir=str(test_settings.generated_assets_dir(project_dir)),
                items=[
                    GeneratedAssetRecord(
                        shot_index=1,
                        backend="openai_image",
                        media_kind="image",
                        status="generated",
                        asset_path=str(test_settings.generated_assets_dir(project_dir) / "shot_001.png"),
                        model="gpt-image-1",
                        prompt="Create a test frame.",
                    )
                ],
            )

            with patch.object(cli, "settings", test_settings):
                with patch(
                    "pipeline.cli.generate_assets_for_plan",
                    side_effect=lambda plan, style_profile, run_parameters, settings, project_dir: (plan, generated_manifest),
                ) as mock_generate_assets:
                    with patch("pipeline.cli.render_plan", return_value=test_settings.video_output_dir / "sample.mp4"):
                        cli.generate(
                            run_config=temp_root / "run_parameters.yaml",
                            script_file=None,
                            output=None,
                            project_dir=None,
                        )

            self.assertTrue(mock_generate_assets.called)
            generated_assets = read_json(test_settings.generated_assets_manifest_path(project_dir))
            self.assertEqual(generated_assets["backend"], "openai_image")
            self.assertEqual(len(generated_assets["items"]), 1)

    def test_run_chains_train_then_generate(self) -> None:
        with patch("pipeline.cli.train") as mock_train:
            with patch("pipeline.cli.generate") as mock_generate:
                cli.run(run_config=Path("/tmp/run_parameters.yaml"))

        mock_train.assert_called_once_with(run_config=Path("/tmp/run_parameters.yaml"))
        mock_generate.assert_called_once_with(run_config=Path("/tmp/run_parameters.yaml"))


def _build_run_parameters() -> RunParameters:
    return RunParameters(
        run_name="sample",
        description="test",
        input_folder="Bundle A",
        script_file="sample1.json",
        output_file="sample.mp4",
        artifact_subdir="sample",
        voiceover_file=None,
        analysis_video_subfolders=[
            "reference_videos",
            "closeups/videos",
            "broll/videos",
        ],
        asset_subfolders={
            "reference_videos": "reference_videos",
            "closeup_videos": "closeups/videos",
            "broll_videos": "broll/videos",
        },
    )


def _build_settings(temp_root: Path) -> Settings:
    app_base_dir = temp_root
    return Settings(
        app_base_dir=app_base_dir,
        scripts_dir=app_base_dir / "Scripts",
        video_input_dir=app_base_dir / "Video Input",
        video_output_dir=app_base_dir / "Video Output",
        pipeline_artifacts_dir=app_base_dir / "artifacts",
        frames_dir_name="frames",
        audio_dir_name="audio",
        generated_assets_dir_name="generated_assets",
        video_analyses_filename="video_analyses.json",
        style_profile_filename="style_profile.json",
        asset_inventory_filename="asset_inventory.json",
        generated_assets_manifest_filename="generated_assets.json",
        shot_plan_filename="shot_plan.json",
        continuity_profile_filename="continuity_profile.json",
        resolved_run_config_filename="resolved_run_config.json",
        openai_api_key=None,
    )


def _write_run_config(
    temp_root: Path,
    run_parameters: RunParameters,
    extra_payload: dict[str, object] | None = None,
) -> None:
    payload = {
        "run_name": run_parameters.run_name,
        "description": run_parameters.description,
        "input_folder": run_parameters.input_folder,
        "script_file": run_parameters.script_file,
        "output_file": run_parameters.output_file,
        "artifact_subdir": run_parameters.artifact_subdir,
        "analysis_video_subfolders": run_parameters.analysis_video_subfolders,
        "asset_subfolders": run_parameters.asset_subfolders,
    }
    if extra_payload:
        payload.update(extra_payload)
    (temp_root / "run_parameters.yaml").write_text(_yaml_dump(payload), encoding="utf-8")


def _write_script_file(temp_root: Path) -> None:
    scripts_dir = temp_root / "Scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "scenes": [
            {
                "name": "Scene 1",
                "description": "Test description.",
                "duration": "4.0",
                "text overlay": "Test overlay",
            }
        ]
    }
    (scripts_dir / "sample1.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _yaml_dump(payload: dict[str, object]) -> str:
    import yaml

    return yaml.safe_dump(payload, sort_keys=False)


if __name__ == "__main__":
    unittest.main()
