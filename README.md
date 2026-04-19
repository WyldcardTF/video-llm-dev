# video-llm-dev

The goal is to create an app that can ingest reference media, understand style and voice patterns, and generate a new draft video from a structured script.

## Current prototype

The current prototype does five main things:

1. Ingest at least one required reference video from a selected input bundle and optionally pick up supporting videos from the rest of that bundle.
2. Train reusable style artifacts from those references by analyzing pacing, motion, brightness, palette, audio cues, and available bundle assets.
3. Generate a motion-aware shot plan from a structured script using the trained artifacts plus continuity rules.
4. Optionally synthesize generated shot assets through an OpenAI image or video backend.
5. Render a draft `.mp4` that prefers generated assets first, then real source-video excerpts, and finally still-image motion as fallback.

This is still a prototype. It is a training-plus-generation-plus-draft-rendering pipeline, not yet a full generative animation system. The repo now has optional real generation backends, but it still does not solve long-range character consistency, scene choreography, or film-quality temporal coherence on its own.

For the deep technical guide, see [docs/tutorial.md](/app/docs/tutorial.md).
For the step-by-step runbook, see [docs/walkthrough.md](/app/docs/walkthrough.md).

## Configuration split

The repo now uses two configuration layers:

### `.env`

Use `.env` for:

1. folder roots and environment paths
2. secrets such as `OPENAI_API_KEY`
3. stable pipeline storage structure

### `run_parameters.yaml`

Use `run_parameters.yaml` for:

1. which input bundle to use via `input_folder`
2. which script file to use
3. which output file to render
4. analysis, planning, render, and model-run settings
5. asset subfolders for the selected run
6. priority video pools inside the bundle

This means you can run the CLI with one YAML file instead of passing many command-line parameters.

Right now, the most important active run parameters are `input_folder`, `script_file`, `output_file`, `artifact_subdir`, `analysis_video_subfolders` as priority sources, `analysis.*`, `planning.*`, `render.fps`, `generation.*`, `models.transcription_model`, `models.image_generation_model`, `models.video_generation_model`, `selection.require_videos`, and `selection.max_reference_videos`. The selected bundle is scanned recursively, so `analysis_video_subfolders` controls discovery priority rather than making every listed folder mandatory.

## Core files

1. [run_parameters.yaml](/app/run_parameters.yaml) is the main per-run config.
2. [Scripts/sample1.json](/app/Scripts/sample1.json) is the current structured script example.
3. [pipeline/run_config.py](/app/pipeline/run_config.py) loads the YAML run config.
4. [pipeline/script_io.py](/app/pipeline/script_io.py) loads structured JSON scripts.

## Run it

Train a run:

```bash
python -m pipeline train --run-config /app/run_parameters.yaml
```

Generate a draft from trained artifacts:

```bash
python -m pipeline generate --run-config /app/run_parameters.yaml
```

Shortcut:

```bash
python -m pipeline run --run-config /app/run_parameters.yaml
```

The intended workflow is:

1. run `train` to build intermediate artifacts such as `video_analyses.json`, `style_profile.json`, and `asset_inventory.json`
2. inspect those artifacts
3. optionally set `generation.backend` plus an image or video model if you want real generated assets
4. run `generate` to create a continuity-aware shot plan, optionally synthesize generated shot assets, and render a draft using the trained style profile and asset inventory

To enable real generation, set `OPENAI_API_KEY` in `.env` and then choose one of these patterns in [`run_parameters.yaml`](/app/run_parameters.yaml):

```yaml
generation:
  backend: openai_image

models:
  image_generation_model: gpt-image-1
```

```yaml
generation:
  backend: openai_video

models:
  video_generation_model: sora-2
```

Inspect the resolved run config:

```bash
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
```

Because `run_parameters.yaml` defaults to the repo root, these also work:

```bash
python -m pipeline train
python -m pipeline generate
```

## Input bundle skeleton

The selected `input_folder` currently points to:

`/app/Video Input/Blonde Blazer Romance`

That bundle now includes a broader skeleton for projects like this:

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

This gives us a better base for future versions that may use stills, 3D assets, brand graphics, storyboards, voiceovers, and music.

Only `reference_videos/` is required to contain at least one supported video for the current pipeline. The rest of the folders are optional supporting inputs and may be missing or empty.

## Structured scripts

The script format is now JSON-first. The current sample in [Scripts/sample1.json](/app/Scripts/sample1.json) includes:

1. top-level project metadata
2. global style metadata
3. a `scenes` list
4. scene-level timing
5. scene-level creative metadata such as `camera`, `mood`, `shot_type`, `text overlay`, and `preferred_asset_types`

Unknown scene fields are preserved in the generated shot plan, so the format is ready to grow with the project.

## Intermediate Artifacts

The most useful files written during a run are:

1. `video_analyses.json`
2. `style_profile.json`
3. `asset_inventory.json`
4. `generated_assets.json`
5. `continuity_profile.json`
6. `shot_plan.json`
7. `generated_assets/`

The shot plan now carries richer fields such as selected asset path, asset type, media kind, clip timing, continuity notes, and generation prompts. The generated-assets manifest records which backend ran, which model was used, what each shot asset path is, and whether a shot fell back to the draft compositor.

## Important notes

1. `.env`, `Video Input`, `Video Output`, and `artifacts` are ignored by Git.
2. `.env.example` is the tracked template.
3. `.dockerignore` also excludes `.env`, `Video Input`, `Video Output`, and `artifacts`.
