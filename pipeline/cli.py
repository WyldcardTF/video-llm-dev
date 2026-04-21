from __future__ import annotations

import re
from dataclasses import asdict, replace
from pathlib import Path

import typer

from .analyze import VideoAnalyzer
from .assets import build_asset_inventory, load_asset_inventory
from .config import get_settings
from .generation import generate_assets_for_plan, resolve_generation_backend
from .ingest import (
    discover_optional_video_files_from_sources,
    merge_unique_video_paths,
)
from .io_utils import ensure_dir, read_json, write_json
from .planning import build_continuity_profile, plan_from_script
from .render import render_plan
from .run_config import RunParameters, load_run_parameters
from .script_io import load_script_file
from .models import (
    AssetInventory,
    ContinuityProfile,
    GenerationPlan,
    ScriptDocument,
    ShotPlanItem,
    StyleProfile,
    VideoAnalysis,
)
from .style import build_style_profile, load_style_profile
from .video_models import list_video_model_presets, resolve_video_model_selection

settings = get_settings()
DEFAULT_RUN_CONFIG_PATH = Path("run_parameters.yaml")

app = typer.Typer(
    help="Prototype pipeline for preparing reusable image/video style artifacts and generating a draft video from a script."
)


def _resolve_script_path(run_parameters: RunParameters, script_override: Path | None) -> Path:
    if script_override is None:
        return run_parameters.script_path(settings)

    candidate = script_override.expanduser()
    if candidate.is_absolute():
        return candidate
    candidates = [
        run_parameters.input_root(settings) / candidate,
        run_parameters.input_root(settings) / "Scripts" / candidate,
        settings.scripts_dir / candidate,
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[1]


def _resolve_output_path(run_parameters: RunParameters, output_override: Path | None) -> Path:
    if output_override is None:
        return run_parameters.output_path(settings)

    candidate = output_override.expanduser()
    if candidate.is_absolute():
        return candidate
    return settings.video_output_dir / candidate


def _next_progressive_output_path(output_path: Path) -> Path:
    output_path = output_path.expanduser()
    parent = output_path.parent
    suffix = output_path.suffix or ".mp4"
    stem = output_path.stem
    match = re.fullmatch(r"(?P<base>.+)_draft(?:_(?P<number>\d+))?", stem)
    if match:
        base_stem = f"{match.group('base')}_draft"
    else:
        base_stem = stem

    pattern = re.compile(rf"^{re.escape(base_stem)}_(\d+){re.escape(suffix)}$")
    existing_numbers = [
        int(found.group(1))
        for candidate in parent.glob(f"{base_stem}_*{suffix}")
        if (found := pattern.fullmatch(candidate.name))
    ]

    if existing_numbers or stem == base_stem:
        return parent / f"{base_stem}_{max(existing_numbers, default=0) + 1}{suffix}"

    if not output_path.exists():
        return output_path

    numbered_pattern = re.compile(rf"^{re.escape(stem)}_(\d+){re.escape(suffix)}$")
    sibling_numbers = [
        int(found.group(1))
        for candidate in parent.glob(f"{stem}_*{suffix}")
        if (found := numbered_pattern.fullmatch(candidate.name))
    ]
    return parent / f"{stem}_{max(sibling_numbers, default=0) + 1}{suffix}"


def _resolve_project_dir(run_parameters: RunParameters, project_dir_override: Path | None) -> Path:
    if project_dir_override is None:
        return run_parameters.project_dir(settings)

    candidate = project_dir_override.expanduser()
    if candidate.is_absolute():
        return candidate
    return settings.pipeline_artifacts_dir / candidate


def _style_profile_for_render(style_profile: StyleProfile, run_parameters: RunParameters) -> StyleProfile:
    dimensions = _render_dimensions(run_parameters)
    if dimensions is None:
        return style_profile
    width, height = dimensions
    return replace(style_profile, target_width=width, target_height=height)


def _render_dimensions(run_parameters: RunParameters) -> tuple[int, int] | None:
    if run_parameters.render.output_width and run_parameters.render.output_height:
        return run_parameters.render.output_width, run_parameters.render.output_height

    aspect_ratio = (run_parameters.generation.video_aspect_ratio or "").strip()
    if aspect_ratio != "9:16":
        return None

    # 1080x1920 is the standard vertical social-video delivery canvas. Kling
    # draft clips may arrive smaller, but fitting during render avoids cropping.
    return 1080, 1920


def _resolve_video_paths(
    run_parameters: RunParameters,
    source_override: Path | None,
    script_document: ScriptDocument | None,
) -> list[Path]:
    script_video_paths = _script_reference_paths(script_document, media_kind="video")
    if source_override is not None:
        override_paths = discover_optional_video_files_from_sources([source_override])
        return merge_unique_video_paths(script_video_paths, override_paths)

    bundle_root = run_parameters.bundle_scan_root(settings)
    if not bundle_root.exists():
        raise FileNotFoundError(f"Selected input_folder does not exist: {bundle_root}")

    video_paths = merge_unique_video_paths(script_video_paths)

    if run_parameters.selection.max_reference_videos:
        video_paths = video_paths[: run_parameters.selection.max_reference_videos]

    return video_paths


def _build_analyzer(run_parameters: RunParameters) -> VideoAnalyzer:
    return VideoAnalyzer(
        sample_frames=run_parameters.analysis.sample_frames,
        timeline_scan_points=run_parameters.analysis.timeline_scan_points,
        transcribe_voice=run_parameters.analysis.transcribe_voice,
        audio_analysis_max_seconds=run_parameters.analysis.audio_analysis_max_seconds,
        transcription_max_seconds=run_parameters.analysis.transcription_max_seconds,
    )


def _train_artifacts(
    run_parameters: RunParameters,
    source_override: Path | None,
    resolved_project_dir: Path,
) -> tuple[list[Path], list[VideoAnalysis], StyleProfile, AssetInventory]:
    script_document = load_script_file(run_parameters.script_path(settings))
    video_paths = _resolve_video_paths(run_parameters, source_override, script_document)
    analyzer = _build_analyzer(run_parameters)
    analyses = analyzer.analyze_many(video_paths, resolved_project_dir) if video_paths else []
    asset_inventory = build_asset_inventory(run_parameters, settings, analyses)
    style_profile = build_style_profile(analyses, _style_inventory_for_script(asset_inventory, script_document))

    _save_resolved_run_config(run_parameters, resolved_project_dir)
    write_json(settings.analyses_path(resolved_project_dir), analyses)
    write_json(settings.style_profile_path(resolved_project_dir), style_profile)
    write_json(settings.asset_inventory_path(resolved_project_dir), asset_inventory)
    return video_paths, analyses, style_profile, asset_inventory


def _script_reference_paths(script_document: ScriptDocument | None, media_kind: str) -> list[Path]:
    if script_document is None:
        return []
    paths: list[Path] = []
    seen: set[Path] = set()
    for scene in script_document.scenes:
        for reference in scene.reference_assets:
            if reference.media_kind != media_kind or reference.path.startswith(("http://", "https://")):
                continue
            path = Path(reference.path).expanduser().resolve()
            if not path.exists() or path in seen:
                continue
            seen.add(path)
            paths.append(path)
    return paths


def _style_inventory_for_script(
    asset_inventory: AssetInventory,
    script_document: ScriptDocument,
) -> AssetInventory:
    active_image_paths = {str(path) for path in _script_reference_paths(script_document, media_kind="image")}
    if not active_image_paths:
        return asset_inventory
    active_items = [
        item
        for item in asset_inventory.items
        if item.media_kind != "image" or item.path in active_image_paths
    ]
    summary: dict[str, int] = {}
    for item in active_items:
        key = f"{item.asset_type}:{item.media_kind}"
        summary[key] = summary.get(key, 0) + 1
    return AssetInventory(items=active_items, summary=dict(sorted(summary.items())))


def _load_trained_style_profile(resolved_project_dir: Path) -> StyleProfile:
    style_profile_path = settings.style_profile_path(resolved_project_dir)
    if not style_profile_path.exists():
        raise FileNotFoundError(
            "No trained style profile was found for this run. "
            f"Expected: {style_profile_path}. "
            "Run `python -m pipeline train` for this run first, or point to the correct project_dir."
        )
    return load_style_profile(style_profile_path)


def _load_trained_asset_inventory(resolved_project_dir: Path) -> AssetInventory:
    asset_inventory_path = settings.asset_inventory_path(resolved_project_dir)
    if not asset_inventory_path.exists():
        raise FileNotFoundError(
            "No trained asset inventory was found for this run. "
            f"Expected: {asset_inventory_path}. "
            "Run `python -m pipeline train` for this run first, or point to the correct project_dir."
        )
    return load_asset_inventory(asset_inventory_path)


def _load_shot_plan(resolved_project_dir: Path) -> GenerationPlan:
    shot_plan_path = settings.shot_plan_path(resolved_project_dir)
    if not shot_plan_path.exists():
        raise FileNotFoundError(
            "No shot plan was found for this run. "
            f"Expected: {shot_plan_path}. "
            "Run `python -m pipeline generate` at least once, or point to the correct project_dir."
        )
    payload = read_json(shot_plan_path)
    if not isinstance(payload, dict):
        raise ValueError(f"Shot plan must be a JSON object: {shot_plan_path}")
    items = [
        ShotPlanItem(**item)
        for item in payload.get("items", [])
        if isinstance(item, dict)
    ]
    return GenerationPlan(
        script=str(payload.get("script", "")),
        total_duration_s=float(payload.get("total_duration_s", 0.0)),
        director_note=str(payload.get("director_note", "")),
        items=items,
        script_format=str(payload.get("script_format", "json")),
        script_source_path=payload.get("script_source_path"),
        continuity_summary=str(payload.get("continuity_summary", "")),
        generation_backend=str(payload.get("generation_backend", "kling")),
        script_metadata=payload.get("script_metadata", {}),
    )


def _save_resolved_run_config(run_parameters: RunParameters, project_dir: Path) -> None:
    if not run_parameters.workflow.save_resolved_run_config:
        return

    payload = {
        "run_parameters": asdict(run_parameters),
        "video_model_selection": asdict(resolve_video_model_selection(run_parameters)),
        "resolved_paths": {
            "script_file": str(run_parameters.script_path(settings)),
            "output_file": str(run_parameters.output_path(settings)),
            "project_dir": str(project_dir),
            "input_root": str(run_parameters.input_root(settings)),
            "bundle_scan_root": str(run_parameters.bundle_scan_root(settings)),
            "video_analyses_file": str(settings.analyses_path(project_dir)),
            "style_profile_file": str(settings.style_profile_path(project_dir)),
            "asset_inventory_file": str(settings.asset_inventory_path(project_dir)),
            "generated_assets_dir": str(settings.generated_assets_dir(project_dir)),
            "generated_assets_manifest_file": str(settings.generated_assets_manifest_path(project_dir)),
            "shot_plan_file": str(settings.shot_plan_path(project_dir)),
            "continuity_profile_file": str(settings.continuity_profile_path(project_dir)),
            "analysis_sources": [str(path) for path in run_parameters.analysis_sources(settings)],
            "asset_paths": run_parameters.resolved_asset_paths(settings),
        },
    }
    write_json(settings.resolved_run_config_path(project_dir), payload)


@app.command()
def train(
    run_config: Path = typer.Option(
        DEFAULT_RUN_CONFIG_PATH,
        help="YAML file describing this model run. Defaults to run_parameters.yaml in the repo root.",
    ),
    source: Path | None = typer.Option(
        None,
        help="Optional override for a video source path to analyze. Videos are optional support data.",
    ),
    project_dir: Path | None = typer.Option(
        None,
        help="Optional override for the artifact output directory. If omitted, the CLI uses artifact_subdir from the YAML run config.",
    ),
) -> None:
    run_parameters = load_run_parameters(run_config)
    resolved_project_dir = ensure_dir(_resolve_project_dir(run_parameters, project_dir))
    video_paths, _analyses, _style_profile, _asset_inventory = _train_artifacts(
        run_parameters,
        source,
        resolved_project_dir,
    )

    media_summary = f"image inputs plus {len(video_paths)} active video reference(s)"
    typer.echo(f"Prepared reusable style artifacts from {media_summary} for run '{run_parameters.run_name}'.")
    typer.echo(f"Training artifacts saved to {resolved_project_dir}")
    typer.echo(f"Style profile saved to {settings.style_profile_path(resolved_project_dir)}")
    typer.echo(f"Asset inventory saved to {settings.asset_inventory_path(resolved_project_dir)}")


@app.command()
def generate(
    run_config: Path = typer.Option(
        DEFAULT_RUN_CONFIG_PATH,
        help="YAML file describing this model run. Defaults to run_parameters.yaml in the repo root.",
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
    style_profile = _load_trained_style_profile(resolved_project_dir)
    asset_inventory = _load_trained_asset_inventory(resolved_project_dir)

    resolved_script_file = _resolve_script_path(run_parameters, script_file)
    script_document = load_script_file(resolved_script_file)
    continuity_profile: ContinuityProfile = build_continuity_profile(script_document, style_profile)
    plan = plan_from_script(
        script_document,
        style_profile,
        planning=run_parameters.planning,
        asset_inventory=asset_inventory,
        continuity_profile=continuity_profile,
        generation_model=run_parameters.models.video_generation_model,
    )
    plan, generated_assets_manifest = generate_assets_for_plan(
        plan=plan,
        style_profile=style_profile,
        run_parameters=run_parameters,
        settings=settings,
        project_dir=resolved_project_dir,
    )

    write_json(settings.shot_plan_path(resolved_project_dir), plan)
    write_json(settings.continuity_profile_path(resolved_project_dir), continuity_profile)
    write_json(settings.generated_assets_manifest_path(resolved_project_dir), generated_assets_manifest)
    _save_resolved_run_config(run_parameters, resolved_project_dir)

    resolved_output = _next_progressive_output_path(_resolve_output_path(run_parameters, output))
    render_style_profile = _style_profile_for_render(style_profile, run_parameters)
    render_path = render_plan(
        plan,
        render_style_profile,
        resolved_output,
        fps=run_parameters.render.fps,
        voiceover_path=run_parameters.voiceover_path(settings),
    )

    typer.echo(f"Loaded trained style profile from {settings.style_profile_path(resolved_project_dir)}")
    typer.echo(f"Loaded trained asset inventory from {settings.asset_inventory_path(resolved_project_dir)}")
    typer.echo(
        "Generation backend: "
        f"{resolve_generation_backend(run_parameters)} "
        f"(manifest: {settings.generated_assets_manifest_path(resolved_project_dir)})"
    )
    model_selection = resolve_video_model_selection(run_parameters)
    typer.echo(
        f"Video model: {model_selection.label} ({model_selection.model}, "
        f"price tier: {model_selection.price_tier})"
    )
    typer.echo(f"Generated plan with {len(plan.items)} shots for run '{run_parameters.run_name}'.")
    typer.echo(f"Draft video saved to {render_path}")


@app.command("render")
def render_existing(
    run_config: Path = typer.Option(
        DEFAULT_RUN_CONFIG_PATH,
        help="YAML file describing this model run. Defaults to run_parameters.yaml in the repo root.",
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
    """Render an existing generated shot plan without calling Kling again."""
    run_parameters = load_run_parameters(run_config)
    resolved_project_dir = ensure_dir(_resolve_project_dir(run_parameters, project_dir))
    ensure_dir(settings.video_output_dir)
    style_profile = _load_trained_style_profile(resolved_project_dir)
    plan = _load_shot_plan(resolved_project_dir)

    resolved_output = _next_progressive_output_path(_resolve_output_path(run_parameters, output))
    render_style_profile = _style_profile_for_render(style_profile, run_parameters)
    render_path = render_plan(
        plan,
        render_style_profile,
        resolved_output,
        fps=run_parameters.render.fps,
        voiceover_path=run_parameters.voiceover_path(settings),
    )
    typer.echo(f"Rendered existing generated assets to {render_path}")


@app.command()
def run(
    run_config: Path = typer.Option(
        DEFAULT_RUN_CONFIG_PATH,
        help="YAML file describing this model run. Defaults to run_parameters.yaml in the repo root.",
    ),
) -> None:
    train(run_config=run_config)
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


@app.command("video-models")
def video_models() -> None:
    """List friendly video model presets accepted by models.video_generation_model."""
    for preset in list_video_model_presets():
        typer.echo(
            f"{preset.preset_id}: {preset.label} | provider={preset.provider} | "
            f"model={preset.model} | price={preset.price_tier} | quality={preset.quality_tier}"
        )


if __name__ == "__main__":
    app()
