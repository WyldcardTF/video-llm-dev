from __future__ import annotations

import unittest

from pipeline.generation import (
    _derive_image_size,
    _derive_video_seconds,
    _derive_video_size,
    resolve_generation_backend,
)
from pipeline.models import StyleProfile
from pipeline.run_config import GenerationParameters, ModelParameters, RunParameters


class GenerationBackendTests(unittest.TestCase):
    def test_resolve_generation_backend_auto_prefers_video_then_image(self) -> None:
        run_parameters = _build_run_parameters(
            generation=GenerationParameters(backend="auto"),
            models=ModelParameters(video_generation_model="sora-2"),
        )
        self.assertEqual(resolve_generation_backend(run_parameters), "openai_video")

        run_parameters = _build_run_parameters(
            generation=GenerationParameters(backend="auto"),
            models=ModelParameters(image_generation_model="gpt-image-1"),
        )
        self.assertEqual(resolve_generation_backend(run_parameters), "openai_image")

    def test_derive_media_sizes_follow_orientation(self) -> None:
        landscape = StyleProfile(
            source_videos=[],
            target_width=1280,
            target_height=720,
            pacing_label="medium",
            preferred_shot_duration_s=4.0,
            average_brightness=0.5,
            average_motion=0.1,
        )
        portrait = StyleProfile(
            source_videos=[],
            target_width=720,
            target_height=1280,
            pacing_label="medium",
            preferred_shot_duration_s=4.0,
            average_brightness=0.5,
            average_motion=0.1,
        )

        self.assertEqual(_derive_image_size(landscape), "1536x1024")
        self.assertEqual(_derive_image_size(portrait), "1024x1536")
        self.assertEqual(_derive_video_size(landscape), "1280x720")
        self.assertEqual(_derive_video_size(portrait), "720x1280")

    def test_derive_video_seconds_matches_supported_buckets(self) -> None:
        self.assertEqual(_derive_video_seconds(3.2), 4)
        self.assertEqual(_derive_video_seconds(7.9), 8)
        self.assertEqual(_derive_video_seconds(10.5), 12)


def _build_run_parameters(
    generation: GenerationParameters | None = None,
    models: ModelParameters | None = None,
) -> RunParameters:
    return RunParameters(
        run_name="sample",
        description="test",
        input_folder="Bundle A",
        script_file="sample1.json",
        output_file="sample.mp4",
        artifact_subdir="sample",
        voiceover_file=None,
        analysis_video_subfolders=["reference_videos"],
        asset_subfolders={"reference_videos": "reference_videos"},
        generation=generation or GenerationParameters(),
        models=models or ModelParameters(),
    )


if __name__ == "__main__":
    unittest.main()
