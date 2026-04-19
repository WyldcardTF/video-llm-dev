from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import typer

from .analyze import VideoAnalyzer
from .config import get_settings
from .ingest import discover_video_files, discover_video_files_from_sources
from .io_utils import ensure_dir, write_json
from .planning import plan_from_script
from .render import render_plan
from .run_config import RunParameters, load_run_parameters
from .script_io import load_script_file
from .style import build_style_profile

settings = get_settings()
DEFAULT_RUN_CONFIG_PATH = Path("run_parameters.yaml")

app = typer.Typer(
    help="Prototype pipeline for ingesting reference videos and generating a style-matched draft video."
)


def _resolve_script_path(run_parameters: RunParameters, script_override: Path | None) -> Path:
    if script_override is None:
        return run_parameters.script_path(settings)

    candidate = script_override.expanduser()
    if candidate.is_absolute():
        return candidate
    return settings.scripts_dir / candidate


def _resolve_output_path(run_parameters: RunParameters, output_override: Path | None) -> Path:
    if output_override is None:
        return run_parameters.output_path(settings)

    candidate = output_override.expanduser()
    if candidate.is_absolute():
        return candidate
    return settings.video_output_dir / candidate


def _resolve_project_dir(run_parameters: RunParameters, project_dir_override: Path | None) -> Path:
    if project_dir_override is None:
        return run_parameters.project_dir(settings)

    candidate = project_dir_override.expanduser()
    if candidate.is_absolute():
        return candidate
    return settings.pipeline_artifacts_dir / candidate


def _resolve_video_paths(run_parameters: RunParameters, source_override: Path | None) -> list[Path]:
    if source_override is not None:
        return discover_video_files(source_override)

    analysis_sources = run_parameters.analysis_sources(settings)
    video_paths = discover_video_files_from_sources(analysis_sources)

    if run_parameters.selection.max_reference_videos:
        video_paths = video_paths[: run_parameters.selection.max_reference_videos]

    return video_paths


def _save_resolved_run_config(run_parameters: RunParameters, project_dir: Path) -> None:
    if not run_parameters.workflow.save_resolved_run_config:
        return

    payload = {
        "run_parameters": asdict(run_parameters),
        "resolved_paths": {
            "script_file": str(run_parameters.script_path(settings)),
            "output_file": str(run_parameters.output_path(settings)),
            "project_dir": str(project_dir),
            "input_root": str(run_parameters.input_root(settings)),
            "analysis_sources": [str(path) for path in run_parameters.analysis_sources(settings)],
            "asset_paths": run_parameters.resolved_asset_paths(settings),
        },
    }
    write_json(settings.resolved_run_config_path(project_dir), payload)


@app.command()
def analyze(
    run_config: Path = typer.Option(
        DEFAULT_RUN_CONFIG_PATH,
        help="YAML file describing this model run. Defaults to run_parameters.yaml in the repo root.",
    ),
    source: Path | None = typer.Option(
        None,
        help="Optional override for the video source path. If omitted, the CLI uses input_folder and analysis_video_subfolders from the YAML run config.",
    ),
    project_dir: Path | None = typer.Option(
        None,
        help="Optional override for the artifact output directory. If omitted, the CLI uses artifact_subdir from the YAML run config.",
    ),
) -> None:
    run_parameters = load_run_parameters(run_config)
    resolved_project_dir = ensure_dir(_resolve_project_dir(run_parameters, project_dir))
    video_paths = _resolve_video_paths(run_parameters, source)

    analyzer = VideoAnalyzer(
        sample_frames=run_parameters.analysis.sample_frames,
        timeline_scan_points=run_parameters.analysis.timeline_scan_points,
        transcribe_voice=run_parameters.analysis.transcribe_voice,
        audio_analysis_max_seconds=run_parameters.analysis.audio_analysis_max_seconds,
        transcription_max_seconds=run_parameters.analysis.transcription_max_seconds,
        openai_transcribe_model=run_parameters.models.transcription_model,
    )
    analyses = analyzer.analyze_many(video_paths, resolved_project_dir)
    style_profile = build_style_profile(analyses)

    _save_resolved_run_config(run_parameters, resolved_project_dir)
    write_json(settings.analyses_path(resolved_project_dir), analyses)
    write_json(settings.style_profile_path(resolved_project_dir), style_profile)

    typer.echo(f"Analyzed {len(analyses)} video(s) for run '{run_parameters.run_name}'.")
    typer.echo(f"Style profile saved to {settings.style_profile_path(resolved_project_dir)}")


@app.command()
def generate(
    run_config: Path = typer.Option(
        DEFAULT_RUN_CONFIG_PATH,
        help="YAML file describing this model run. Defaults to run_parameters.yaml in the repo root.",
    ),
    source: Path | None = typer.Option(
        None,
        help="Optional override for the video source path. If omitted, the CLI uses input_folder and analysis_video_subfolders from the YAML run config.",
    ),
    script_file: Path | None = typer.Option(
        None,
        help="Optional override for the structured script file. If omitted, the CLI uses script_file from the YAML run config.",
    ),
    output: Path | None = typer.Option(
        None,
        help="Optional override for the output video path. If omitted, the CLI uses output_file from the YAML run config.",
    ),
    project_dir: Path | None = typer.Option(
        None,
        help="Optional override for the artifact output directory. If omitted, the CLI uses artifact_subdir from the YAML run config.",
    ),
) -> None:
    run_parameters = load_run_parameters(run_config)
    resolved_project_dir = ensure_dir(_resolve_project_dir(run_parameters, project_dir))
    ensure_dir(settings.video_output_dir)

    video_paths = _resolve_video_paths(run_parameters, source)
    analyzer = VideoAnalyzer(
        sample_frames=run_parameters.analysis.sample_frames,
        timeline_scan_points=run_parameters.analysis.timeline_scan_points,
        transcribe_voice=run_parameters.analysis.transcribe_voice,
        audio_analysis_max_seconds=run_parameters.analysis.audio_analysis_max_seconds,
        transcription_max_seconds=run_parameters.analysis.transcription_max_seconds,
        openai_transcribe_model=run_parameters.models.transcription_model,
    )
    analyses = analyzer.analyze_many(video_paths, resolved_project_dir)
    style_profile = build_style_profile(analyses)

    resolved_script_file = _resolve_script_path(run_parameters, script_file)
    script_document = load_script_file(resolved_script_file)
    plan = plan_from_script(script_document, style_profile, planning=run_parameters.planning)

    write_json(settings.analyses_path(resolved_project_dir), analyses)
    write_json(settings.style_profile_path(resolved_project_dir), style_profile)
    write_json(settings.shot_plan_path(resolved_project_dir), plan)
    _save_resolved_run_config(run_parameters, resolved_project_dir)

    resolved_output = _resolve_output_path(run_parameters, output)
    render_path = render_plan(
        plan,
        style_profile,
        resolved_output,
        fps=run_parameters.render.fps,
        voiceover_path=run_parameters.voiceover_path(settings),
    )

    typer.echo(f"Generated plan with {len(plan.items)} shots for run '{run_parameters.run_name}'.")
    typer.echo(f"Draft video saved to {render_path}")


@app.command()
def run(
    run_config: Path = typer.Option(
        DEFAULT_RUN_CONFIG_PATH,
        help="YAML file describing this model run. Defaults to run_parameters.yaml in the repo root.",
    ),
) -> None:
    generate(run_config=run_config)


@app.command("show-run-config")
def show_run_config(
    run_config: Path = typer.Option(
        DEFAULT_RUN_CONFIG_PATH,
        help="YAML file describing this model run. Defaults to run_parameters.yaml in the repo root.",
    ),
) -> None:
    run_parameters = load_run_parameters(run_config)
    typer.echo(asdict(run_parameters))


if __name__ == "__main__":
    app()
