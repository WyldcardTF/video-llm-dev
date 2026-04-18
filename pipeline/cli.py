from __future__ import annotations

from pathlib import Path

import typer

from .analyze import VideoAnalyzer
from .ingest import discover_video_files
from .io_utils import ensure_dir, read_text, write_json
from .planning import plan_from_script
from .render import render_plan
from .style import build_style_profile

app = typer.Typer(
    help="Prototype pipeline for ingesting reference videos and generating a style-matched draft video."
)


@app.command()
def analyze(
    source: Path = typer.Option(..., help="A video file or a directory full of reference videos."),
    project_dir: Path = typer.Option(Path("artifacts/session"), help="Where analysis outputs should be stored."),
    sample_frames: int = typer.Option(6, min=3, help="How many frames to sample from each reference video."),
    transcribe_voice: bool = typer.Option(
        False,
        help="Use the OpenAI transcription API when OPENAI_API_KEY is set.",
    ),
) -> None:
    project_dir = ensure_dir(project_dir)
    video_paths = discover_video_files(source)
    analyzer = VideoAnalyzer(sample_frames=sample_frames, transcribe_voice=transcribe_voice)
    analyses = analyzer.analyze_many(video_paths, project_dir)
    style_profile = build_style_profile(analyses)

    write_json(project_dir / "video_analyses.json", analyses)
    write_json(project_dir / "style_profile.json", style_profile)

    typer.echo(f"Analyzed {len(analyses)} video(s).")
    typer.echo(f"Style profile saved to {project_dir / 'style_profile.json'}")


@app.command()
def generate(
    source: Path = typer.Option(..., help="A video file or a directory full of reference videos."),
    script_file: Path = typer.Option(..., help="The narration or script text to turn into a draft."),
    project_dir: Path = typer.Option(Path("artifacts/session"), help="Where outputs should be stored."),
    output: Path = typer.Option(Path("artifacts/session/generated/draft.mp4"), help="Rendered draft video path."),
    sample_frames: int = typer.Option(6, min=3, help="How many frames to sample from each reference video."),
    transcribe_voice: bool = typer.Option(
        False,
        help="Use the OpenAI transcription API when OPENAI_API_KEY is set.",
    ),
    voiceover_file: Path | None = typer.Option(
        None,
        help="Optional narration file to mux into the rendered video.",
    ),
) -> None:
    project_dir = ensure_dir(project_dir)
    generated_dir = ensure_dir(project_dir / "generated")
    video_paths = discover_video_files(source)
    analyzer = VideoAnalyzer(sample_frames=sample_frames, transcribe_voice=transcribe_voice)
    analyses = analyzer.analyze_many(video_paths, project_dir)
    style_profile = build_style_profile(analyses)
    script = read_text(script_file)
    plan = plan_from_script(script, style_profile)

    write_json(project_dir / "video_analyses.json", analyses)
    write_json(project_dir / "style_profile.json", style_profile)
    write_json(project_dir / "shot_plan.json", plan)

    resolved_output = output if output.is_absolute() else generated_dir / output.name
    render_path = render_plan(plan, style_profile, resolved_output, voiceover_path=voiceover_file)

    typer.echo(f"Generated plan with {len(plan.items)} shots.")
    typer.echo(f"Draft video saved to {render_path}")


@app.command()
def run(
    source: Path = typer.Option(..., help="A video file or a directory full of reference videos."),
    script_file: Path = typer.Option(..., help="The narration or script text to turn into a draft."),
    project_dir: Path = typer.Option(Path("artifacts/session"), help="Where outputs should be stored."),
    transcribe_voice: bool = typer.Option(
        False,
        help="Use the OpenAI transcription API when OPENAI_API_KEY is set.",
    ),
) -> None:
    generate(
        source=source,
        script_file=script_file,
        project_dir=project_dir,
        output=project_dir / "generated" / "draft.mp4",
        sample_frames=6,
        transcribe_voice=transcribe_voice,
        voiceover_file=None,
    )


if __name__ == "__main__":
    app()
