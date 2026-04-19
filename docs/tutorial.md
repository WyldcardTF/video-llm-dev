# Pipeline Tutorial

This is the deep-dive document for the current prototype. Its job is to teach the system, not just tell you which command to run.

If you want the practical runbook instead, use [walkthrough.md](./walkthrough.md).

## What This Pipeline Does

At a high level, the pipeline turns a project bundle plus a script into a draft video:

`input bundle -> video discovery -> analysis -> style profile -> script loading -> shot plan -> draft render`

The current prototype is not yet a full generative video system. It does four concrete things today:

1. Finds videos inside a selected project bundle.
2. Analyzes those videos for style and audio signals.
3. Converts a script into a structured shot plan.
4. Renders a draft `.mp4` using sampled reference frames and overlay text.

The most important design idea is that the repo splits stable environment configuration from per-run creative configuration:

1. `.env` defines folder roots, artifact names, and secrets.
2. `run_parameters.yaml` defines one specific run.
3. `Scripts/sample1.json` defines the scenes for that run.

## Repo Map

The files worth understanding first are:

1. [`pipeline/config.py`](../pipeline/config.py) loads `.env` and resolves global paths.
2. [`pipeline/run_config.py`](../pipeline/run_config.py) loads `run_parameters.yaml`.
3. [`pipeline/cli.py`](../pipeline/cli.py) defines the commands and the run flow.
4. [`pipeline/ingest.py`](../pipeline/ingest.py) discovers supported video files.
5. [`pipeline/analyze.py`](../pipeline/analyze.py) extracts style and audio signals from videos.
6. [`pipeline/style.py`](../pipeline/style.py) aggregates many `VideoAnalysis` objects into one `StyleProfile`.
7. [`pipeline/script_io.py`](../pipeline/script_io.py) loads JSON or text scripts.
8. [`pipeline/planning.py`](../pipeline/planning.py) turns scenes into a `GenerationPlan`.
9. [`pipeline/render.py`](../pipeline/render.py) renders the final draft video.
10. [`pipeline/models.py`](../pipeline/models.py) defines the handoff dataclasses used between stages.

## Stage 1: Global Settings From `.env`

The first configuration layer is the environment. `pipeline/config.py` loads `.env` and resolves the folder roots used everywhere else.

Core behavior:

```python
app_base_dir = _as_path(_env_text("APP_BASE_DIR", "/app") or "/app", Path.cwd())
scripts_dir = _env_path("SCRIPTS_DIR", "Scripts", app_base_dir)
video_input_dir = _env_path("VIDEO_INPUT_DIR", "Video Input", app_base_dir)
video_output_dir = _env_path("VIDEO_OUTPUT_DIR", "Video Output", app_base_dir)
```

What this means:

1. The repo assumes `/app` by default.
2. Scripts live under `Scripts/` unless you override them.
3. Input bundles live under `Video Input/`.
4. Rendered videos go to `Video Output/`.
5. Pipeline artifacts go to `artifacts/`.

This split matters because it keeps machine-specific path setup out of the run-specific YAML.

Typical things that belong in `.env`:

1. `OPENAI_API_KEY`
2. alternate root directories
3. artifact filenames
4. frame and audio folder naming

## Stage 2: Per-Run Configuration From YAML

The second configuration layer is [`run_parameters.yaml`](../run_parameters.yaml). This file defines one run of the pipeline.

The loader in [`pipeline/run_config.py`](../pipeline/run_config.py) builds a `RunParameters` dataclass and a few nested parameter groups:

1. `analysis`
2. `planning`
3. `render`
4. `models`
5. `selection`
6. `workflow`

Here is the shape of the main object:

```python
@dataclass(frozen=True)
class RunParameters:
    run_name: str
    description: str
    input_folder: str
    script_file: str
    output_file: str
    artifact_subdir: str
    voiceover_file: str | None
    analysis_video_subfolders: list[str]
    asset_subfolders: dict[str, str]
```

### The Most Important Fields

`input_folder`

This selects the project bundle under `Video Input/`. For the sample repo, the selected bundle is:

`/app/Video Input/Blonde Blazer Romance`

`script_file`

This points to a script in `Scripts/` unless you give an absolute path.

`output_file`

This points to `Video Output/` unless you give an absolute path.

`artifact_subdir`

This decides where analysis artifacts and plans are written under `artifacts/`.

`analysis_video_subfolders`

This is a priority list of video pools inside the bundle. It does not mean every folder must exist or contain videos.

`asset_subfolders.reference_videos`

This is the one path that matters for required-video validation when `selection.require_videos: true`.

## Stage 3: The Input Bundle Contract

The selected input bundle is the project folder the pipeline works from.

The important rule today is:

1. `reference_videos/` must contain at least one supported video.
2. Every other folder is optional supporting input.

The sample bundle includes folders like:

1. `reference_videos/`
2. `closeups/videos/`
3. `closeups/images/`
4. `broll/videos/`
5. `broll/images/`
6. `testimonials/videos/`
7. `portraits/`
8. `product_shots/`
9. `3d_models/`
10. `style_references/`
11. `brand_assets/`
12. `overlays/`
13. `audio/voiceovers/`
14. `audio/music/`
15. `audio/sfx/`
16. `docs/storyboards/`
17. `docs/transcripts/`

Some of those folders are future-facing. They are part of the project shape even if the current renderer does not actively consume them yet.

## Stage 4: How Video Discovery Actually Works

The discovery flow lives across [`pipeline/cli.py`](../pipeline/cli.py), [`pipeline/run_config.py`](../pipeline/run_config.py), and [`pipeline/ingest.py`](../pipeline/ingest.py).

The important logic is:

```python
required_source = run_parameters.required_reference_video_source(settings)
required_videos = discover_video_files(required_source)

prioritized_supporting_videos = discover_optional_video_files_from_sources(
    run_parameters.analysis_sources(settings)
)
bundle_videos = discover_video_files(bundle_root)

video_paths = merge_unique_video_paths(
    required_videos,
    prioritized_supporting_videos,
    bundle_videos,
)
```

Read that in plain English:

1. Validate that `reference_videos` contains at least one supported video.
2. Search the configured priority subfolders for optional supporting videos.
3. Scan the entire selected bundle recursively for any other videos.
4. Merge everything in priority order and remove duplicates.

This gives you a useful balance:

1. the run still has one guaranteed reference source
2. optional folders can be empty without breaking the run
3. stray supporting videos in subfolders are still discovered

### Supported Video Extensions

The allowed extensions are defined in [`pipeline/ingest.py`](../pipeline/ingest.py):

```python
VIDEO_EXTENSIONS = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
}
```

## Stage 5: CLI Commands And Their Roles

The CLI is defined in [`pipeline/cli.py`](../pipeline/cli.py).

The commands are:

1. `python -m pipeline analyze`
2. `python -m pipeline generate`
3. `python -m pipeline run`
4. `python -m pipeline show-run-config`

### `show-run-config`

This is the safest first command because it shows you how the YAML resolves before any heavy work starts.

```bash
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
```

Use it to verify:

1. the selected bundle
2. the resolved script path
3. the resolved output path
4. the selected analysis and planning parameters

### `analyze`

This command stops after analysis and style aggregation.

```bash
python -m pipeline analyze --run-config /app/run_parameters.yaml
```

Outputs:

1. `video_analyses.json`
2. `style_profile.json`
3. sampled frames
4. optionally a transcription sample
5. `resolved_run_config.json`

### `generate`

This is the full flow:

```bash
python -m pipeline generate --run-config /app/run_parameters.yaml
```

It performs:

1. input discovery
2. analysis
3. style aggregation
4. script loading
5. planning
6. rendering

### `run`

This is just a shorthand for `generate`.

## Stage 6: Video Analysis

The analyzer lives in [`pipeline/analyze.py`](../pipeline/analyze.py). It opens each video with OpenCV and extracts:

1. sample frames
2. brightness
3. motion and shot pacing heuristics
4. a simple color palette
5. audio levels
6. optional speech transcription

### Sample Frames

The analyzer samples frames across the timeline:

```python
timestamps = np.linspace(
    max(duration_s * 0.05, 0.0),
    max(duration_s * 0.95, 0.0),
    num=self.sample_frames,
)
```

That means it avoids only sampling the first and last instant and instead spreads samples through most of the clip.

### Motion And Pacing

The current pacing logic is heuristic-based, not ML-based. It compares resized grayscale frames across timeline scan points and estimates:

1. how much adjacent sampled frames differ
2. how many cuts are likely happening
3. an estimated shot length

Those estimates feed into later planning.

### Audio

Audio analysis is done with `ffmpeg`. The pipeline extracts mono PCM samples, then computes:

1. `mean_level`
2. `peak_level`
3. `silence_ratio`

If transcription is enabled and an API key is available, it also sends an extracted audio sample to OpenAI transcription.

## Stage 7: Style Aggregation

The style aggregation step lives in [`pipeline/style.py`](../pipeline/style.py).

Its job is to collapse many `VideoAnalysis` objects into one `StyleProfile`.

The current aggregation computes:

1. most common resolution
2. average brightness
3. average motion
4. average preferred shot duration
5. combined color palette
6. combined voice-style description
7. a list of reference images from sampled frames

The pacing label is derived like this:

```python
if preferred_shot_duration_s <= 2.5:
    pacing_label = "fast"
elif preferred_shot_duration_s <= 4.5:
    pacing_label = "medium"
else:
    pacing_label = "slow"
```

This matters because the planner uses the style profile later when it fills in missing duration or transition decisions.

## Stage 8: Script Loading

The script loader is in [`pipeline/script_io.py`](../pipeline/script_io.py).

It supports two formats:

1. JSON scene documents
2. plain-text fallback scripts

JSON is the main path now.

### JSON Scene Format

The sample file [`Scripts/sample1.json`](../Scripts/sample1.json) includes:

1. top-level project metadata
2. top-level style metadata
3. a `scenes` list
4. per-scene duration and timing
5. per-scene creative fields

The loader accepts multiple naming variants. For example:

1. `text overlay`
2. `text_overlay`
3. `overlay_text`
4. `caption`

All of those normalize into the same scene field.

### Unknown Fields Are Preserved

One useful design choice is that unrecognized scene keys are not dropped. They are stored in `scene.metadata`.

That makes the format easy to grow. You can add fields such as:

1. `lens`
2. `location`
3. `wardrobe`
4. `cta`
5. `preferred_asset_types`

without breaking the loader.

### Duration Parsing

The loader can parse:

1. labeled time like `00h:00m:04s:00ms`
2. colon time like `00:00:04.000`
3. raw numeric seconds like `4.0`

If `duration` is missing but `time_start` and `time_end` exist, it derives duration from them.

## Stage 9: Planning

The planning logic lives in [`pipeline/planning.py`](../pipeline/planning.py).

Its job is to turn scenes into `ShotPlanItem` objects inside a `GenerationPlan`.

Each shot plan item contains:

1. title
2. narration
3. duration
4. visual direction
5. reference image
6. overlay text
7. transition
8. timing metadata
9. preserved scene metadata

### Duration Resolution

The duration logic is:

```python
if planning.honor_script_timing and scene.duration_s:
    return max(planning.shot_duration_min_s, min(scene.duration_s, planning.shot_duration_max_s))
```

If the script gives an explicit duration and `honor_script_timing` is enabled, the planner uses it directly within the configured min/max limits.

Otherwise it estimates a duration from:

1. scene word count
2. style profile pacing
3. preferred shot duration
4. configured min/max shot lengths

### Visual Direction Generation

The current planner builds a text prompt-like description for each shot. It combines:

1. scene name
2. scene description
3. pacing label
4. dominant colors
5. voice style
6. optionally preserved scene metadata
7. timing details

This is important because the render stage is simple today, but the plan is already structured enough for future image or video generation stages.

## Stage 10: Rendering

The renderer lives in [`pipeline/render.py`](../pipeline/render.py).

It is intentionally modest. The goal is to prove that earlier stages produce enough structure to drive a visible output.

The renderer currently does this for each shot:

1. choose a reference image
2. resize it to cover the output frame
3. apply a gentle animated zoom/pan
4. draw a lower-third style text panel
5. write the frames into an `.mp4`
6. optionally mux voiceover audio

The core idea:

```python
background = _load_background(item, style_profile, frame_size)
animated = _apply_motion(background, progress, item.index)
composited = _draw_overlay(animated, item, style_profile)
```

So even though the renderer is simple, it still reflects real decisions made earlier:

1. reference imagery comes from analyzed videos
2. titles and text overlays come from the script
3. frame size comes from the style profile
4. voiceover can be attached if configured

## Stage 11: Data Models And Handoffs

The dataclasses in [`pipeline/models.py`](../pipeline/models.py) are the contract between stages.

The most important ones are:

`VideoAnalysis`

Represents what the analyzer learned from one source video.

`StyleProfile`

Represents the combined visual and audio style target for the run.

`ScriptDocument`

Represents the parsed script and its scenes.

`ShotPlanItem`

Represents one planned shot in the generated sequence.

`GenerationPlan`

Represents the full draft video plan before rendering.

Understanding these objects is the easiest way to understand the system architecture, because each stage mostly transforms one dataclass into another.

## Stage 12: What Gets Written To Disk

A typical run writes:

1. `artifacts/<artifact_subdir>/resolved_run_config.json`
2. `artifacts/<artifact_subdir>/video_analyses.json`
3. `artifacts/<artifact_subdir>/style_profile.json`
4. `artifacts/<artifact_subdir>/shot_plan.json`
5. `artifacts/<artifact_subdir>/frames/...`
6. `artifacts/<artifact_subdir>/audio/...`
7. `Video Output/<output_file>`

This makes the pipeline inspectable. You can debug stage by stage instead of treating it like a black box.

## Stage 13: Read The Sample Run End To End

If you want to inspect the current sample run with code and artifacts side by side, use this sequence:

```bash
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
python -m json.tool /app/Scripts/sample1.json
python -m pipeline analyze --run-config /app/run_parameters.yaml
python -m json.tool /app/artifacts/sample1/resolved_run_config.json | sed -n '1,260p'
python -m json.tool /app/artifacts/sample1/video_analyses.json | sed -n '1,220p'
python -m json.tool /app/artifacts/sample1/style_profile.json | sed -n '1,220p'
python -m pipeline generate --run-config /app/run_parameters.yaml
python -m json.tool /app/artifacts/sample1/shot_plan.json | sed -n '1,260p'
ls -lh "/app/Video Output"
```

As you inspect the output, ask:

1. Did it pick up the right videos?
2. Did it tolerate empty optional folders?
3. Does the style profile feel plausible?
4. Do the shot durations match your intent?
5. Does the rendered draft reflect the script structure?

## Stage 14: Active Behavior Vs Future-Facing Structure

The pipeline already uses these fields actively:

1. `input_folder`
2. `script_file`
3. `output_file`
4. `artifact_subdir`
5. `voiceover_file`
6. `analysis_video_subfolders`
7. `analysis.*`
8. `planning.*`
9. `render.fps`
10. `models.transcription_model`
11. `selection.preferred_reference_types`
12. `selection.require_videos`
13. `selection.max_reference_videos`
14. `workflow.save_resolved_run_config`

These fields are mostly structural placeholders today:

1. many non-video asset pools in `asset_subfolders`
2. `render.output_width`
3. `render.output_height`
4. `models.image_generation_model`
5. `models.video_generation_model`
6. `models.voice_generation_model`
7. `selection.allow_images_as_fallback`
8. `workflow.reuse_existing_analysis`

That does not make them useless. They define the project shape the repo is growing into.

## Stage 15: Good Ways To Extend This Repo

If you keep building on this system, the most natural next improvements are:

1. add caching so analysis can be reused across runs
2. use image and asset pools directly during rendering
3. improve shot detection beyond simple motion heuristics
4. align the plan to real voiceover timing
5. generate prompts intentionally from scene metadata
6. add more tests around run-config loading and CLI flows

## Summary

The mental model to keep is:

1. `config.py` decides where everything lives
2. `run_config.py` decides what this run means
3. `ingest.py` decides which videos count
4. `analyze.py` decides what those videos imply stylistically
5. `script_io.py` decides what the script says structurally
6. `planning.py` turns style plus script into a plan
7. `render.py` turns the plan into a visible draft

Once that model clicks, the repo becomes much easier to modify confidently.
