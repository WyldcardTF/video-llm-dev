from __future__ import annotations

from pathlib import Path

import typer

from .analyze import VideoAnalyzer
from .config import get_settings
from .ingest import discover_video_files
from .io_utils import ensure_dir, read_text, write_json
from .planning import plan_from_script
from .render import render_plan
from .style import build_style_profile

settings = get_settings()

app = typer.Typer(
    help="Prototype pipeline for ingesting reference videos and generating a style-matched draft video."
)


def _resolve_output_path(output: Path) -> Path:
    if output.is_absolute():
        return output
    return settings.video_output_dir / output


@app.command()
def analyze(
    source: Path = typer.Option(
        settings.default_source(),
        help="A video file or a directory full of reference videos. Defaults to PIPELINE_SOURCE_PATH or VIDEO_INPUT_DIR from .env.",
    ),
    project_dir: Path = typer.Option(
        settings.pipeline_project_dir,
        help="Where analysis outputs should be stored. Defaults to PIPELINE_PROJECT_DIR from .env.",
    ),
    sample_frames: int = typer.Option(
        settings.sample_frames,
        min=3,
        help="How many frames to sample from each reference video. Defaults to SAMPLE_FRAMES from .env.",
    ),
    timeline_scan_points: int = typer.Option(
        settings.timeline_scan_points,
        min=12,
        help="How many points to scan when estimating motion and pacing. Defaults to TIMELINE_SCAN_POINTS from .env.",
    ),
    transcribe_voice: bool = typer.Option(
        settings.transcribe_voice,
        help="Use the OpenAI transcription API when OPENAI_API_KEY is set. Defaults to TRANSCRIBE_VOICE from .env.",
    ),
) -> None:
    project_dir = ensure_dir(project_dir)
    video_paths = discover_video_files(source)
    analyzer = VideoAnalyzer(
        sample_frames=sample_frames,
        timeline_scan_points=timeline_scan_points,
        transcribe_voice=transcribe_voice,
    )
    analyses = analyzer.analyze_many(video_paths, project_dir)
    style_profile = build_style_profile(analyses)

    write_json(settings.analyses_path(project_dir), analyses)
    write_json(settings.style_profile_path(project_dir), style_profile)

    typer.echo(f"Analyzed {len(analyses)} video(s).")
    typer.echo(f"Style profile saved to {settings.style_profile_path(project_dir)}")


@app.command()
def generate(
    source: Path = typer.Option(
        settings.default_source(),
        help="A video file or a directory full of reference videos. Defaults to PIPELINE_SOURCE_PATH or VIDEO_INPUT_DIR from .env.",
    ),
    script_file: Path = typer.Option(
        settings.script_input_file,
        help="The narration or script text to turn into a draft. Defaults to SCRIPT_INPUT_FILE from .env.",
    ),
    project_dir: Path = typer.Option(
        settings.pipeline_project_dir,
        help="Where intermediate outputs should be stored. Defaults to PIPELINE_PROJECT_DIR from .env.",
    ),
    output: Path = typer.Option(
        settings.default_output_path(),
        help="Rendered draft video path. Defaults to VIDEO_OUTPUT_DIR + OUTPUT_FILENAME from .env.",
    ),
    sample_frames: int = typer.Option(
        settings.sample_frames,
        min=3,
        help="How many frames to sample from each reference video. Defaults to SAMPLE_FRAMES from .env.",
    ),
    timeline_scan_points: int = typer.Option(
        settings.timeline_scan_points,
        min=12,
        help="How many points to scan when estimating motion and pacing. Defaults to TIMELINE_SCAN_POINTS from .env.",
    ),
    transcribe_voice: bool = typer.Option(
        settings.transcribe_voice,
        help="Use the OpenAI transcription API when OPENAI_API_KEY is set. Defaults to TRANSCRIBE_VOICE from .env.",
    ),
    voiceover_file: Path | None = typer.Option(
        settings.voiceover_input_file,
        help="Optional narration file to mux into the rendered video. Defaults to VOICEOVER_INPUT_FILE from .env.",
    ),
    render_fps: int = typer.Option(
        settings.render_fps,
        min=1,
        help="Output video frame rate. Defaults to RENDER_FPS from .env.",
    ),
) -> None:
    project_dir = ensure_dir(project_dir)
    ensure_dir(settings.video_output_dir)
    video_paths = discover_video_files(source)
    analyzer = VideoAnalyzer(
        sample_frames=sample_frames,
        timeline_scan_points=timeline_scan_points,
        transcribe_voice=transcribe_voice,
    )
    analyses = analyzer.analyze_many(video_paths, project_dir)
    style_profile = build_style_profile(analyses)
    script = read_text(script_file)
    plan = plan_from_script(script, style_profile)

    write_json(settings.analyses_path(project_dir), analyses)
    write_json(settings.style_profile_path(project_dir), style_profile)
    write_json(settings.shot_plan_path(project_dir), plan)

    resolved_output = _resolve_output_path(output)
    render_path = render_plan(
        plan,
        style_profile,
        resolved_output,
        fps=render_fps,
        voiceover_path=voiceover_file,
    )

    typer.echo(f"Generated plan with {len(plan.items)} shots.")
    typer.echo(f"Draft video saved to {render_path}")


@app.command()
def run(
    source: Path = typer.Option(
        settings.default_source(),
        help="A video file or a directory full of reference videos. Defaults to PIPELINE_SOURCE_PATH or VIDEO_INPUT_DIR from .env.",
    ),
    script_file: Path = typer.Option(
        settings.script_input_file,
        help="The narration or script text to turn into a draft. Defaults to SCRIPT_INPUT_FILE from .env.",
    ),
    project_dir: Path = typer.Option(
        settings.pipeline_project_dir,
        help="Where intermediate outputs should be stored. Defaults to PIPELINE_PROJECT_DIR from .env.",
    ),
    output: Path = typer.Option(
        settings.default_output_path(),
        help="Rendered draft video path. Defaults to VIDEO_OUTPUT_DIR + OUTPUT_FILENAME from .env.",
    ),
    sample_frames: int = typer.Option(
        settings.sample_frames,
        min=3,
        help="How many frames to sample from each reference video. Defaults to SAMPLE_FRAMES from .env.",
    ),
    timeline_scan_points: int = typer.Option(
        settings.timeline_scan_points,
        min=12,
        help="How many points to scan when estimating motion and pacing. Defaults to TIMELINE_SCAN_POINTS from .env.",
    ),
    transcribe_voice: bool = typer.Option(
        settings.transcribe_voice,
        help="Use the OpenAI transcription API when OPENAI_API_KEY is set. Defaults to TRANSCRIBE_VOICE from .env.",
    ),
    voiceover_file: Path | None = typer.Option(
        settings.voiceover_input_file,
        help="Optional narration file to mux into the rendered video. Defaults to VOICEOVER_INPUT_FILE from .env.",
    ),
    render_fps: int = typer.Option(
        settings.render_fps,
        min=1,
        help="Output video frame rate. Defaults to RENDER_FPS from .env.",
    ),
) -> None:
    generate(
        source=source,
        script_file=script_file,
        project_dir=project_dir,
        output=output,
        sample_frames=sample_frames,
        timeline_scan_points=timeline_scan_points,
        transcribe_voice=transcribe_voice,
        voiceover_file=voiceover_file,
        render_fps=render_fps,
    )


if __name__ == "__main__":
    app()
