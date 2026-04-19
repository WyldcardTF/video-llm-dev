from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline import cli
from pipeline.config import Settings
from pipeline.ingest import (
    discover_optional_video_files,
    merge_unique_video_paths,
)
from pipeline.run_config import RunParameters


class VideoDiscoveryTests(unittest.TestCase):
    def test_discover_optional_video_files_skips_missing_empty_and_non_video_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            empty_dir = root / "empty"
            empty_dir.mkdir()
            image_path = root / "still.jpg"
            image_path.write_text("not a video", encoding="utf-8")

            self.assertEqual(discover_optional_video_files(root / "missing"), [])
            self.assertEqual(discover_optional_video_files(empty_dir), [])
            self.assertEqual(discover_optional_video_files(image_path), [])

    def test_merge_unique_video_paths_preserves_priority_order(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            first = root / "first.mp4"
            second = root / "second.mp4"
            third = root / "third.mp4"
            for path in (first, second, third):
                path.write_bytes(b"video")

            merged = merge_unique_video_paths(
                [second, first],
                [first, third],
                [third, second],
            )

            self.assertEqual(
                merged,
                [second.resolve(), first.resolve(), third.resolve()],
            )

    def test_resolve_video_paths_requires_reference_videos_but_scans_bundle_recursively(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            bundle_root = temp_root / "Video Input" / "Bundle A"
            reference_video = bundle_root / "reference_videos" / "hero.mp4"
            supporting_video = bundle_root / "broll" / "videos" / "detail.mp4"
            nested_video = bundle_root / "extras" / "nested" / "bonus.mp4"

            for video_path in (reference_video, supporting_video, nested_video):
                video_path.parent.mkdir(parents=True, exist_ok=True)
                video_path.write_bytes(b"video")

            (bundle_root / "closeups" / "videos").mkdir(parents=True, exist_ok=True)

            run_parameters = _build_run_parameters()
            test_settings = _build_settings(temp_root)

            with patch.object(cli, "settings", test_settings):
                resolved_videos = cli._resolve_video_paths(run_parameters, None)

            self.assertEqual(
                resolved_videos,
                [
                    reference_video.resolve(),
                    supporting_video.resolve(),
                    nested_video.resolve(),
                ],
            )

    def test_resolve_video_paths_fails_when_reference_videos_is_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            bundle_root = temp_root / "Video Input" / "Bundle A"
            (bundle_root / "reference_videos").mkdir(parents=True, exist_ok=True)
            supporting_video = bundle_root / "broll" / "videos" / "detail.mp4"
            supporting_video.parent.mkdir(parents=True, exist_ok=True)
            supporting_video.write_bytes(b"video")

            run_parameters = _build_run_parameters()
            test_settings = _build_settings(temp_root)

            with patch.object(cli, "settings", test_settings):
                with self.assertRaises(FileNotFoundError) as exc_info:
                    cli._resolve_video_paths(run_parameters, None)

            self.assertIn("must contain at least one supported video", str(exc_info.exception))
            self.assertIn("reference_videos", str(exc_info.exception))


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
        video_analyses_filename="video_analyses.json",
        style_profile_filename="style_profile.json",
        shot_plan_filename="shot_plan.json",
        resolved_run_config_filename="resolved_run_config.json",
        openai_api_key=None,
    )


if __name__ == "__main__":
    unittest.main()
