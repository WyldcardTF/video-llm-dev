# video-llm-dev

The goal is to create an app that can ingest reference media, understand style and voice patterns, and generate a new draft video from a structured script.

## Current prototype

The current prototype does four main things:

1. Ingest reference videos from a selected input bundle.
2. Analyze visual style signals such as pacing, motion, brightness, and palette.
3. Analyze audio energy and optionally transcribe voice with OpenAI.
4. Convert a structured script into a shot plan and render a draft `.mp4`.

This is still a prototype. It is a style-analysis and draft-rendering pipeline, not yet a full generative video production system.

For the detailed walkthrough, see [docs/tutorial.md](/app/docs/tutorial.md).

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

This means you can run the CLI with one YAML file instead of passing many command-line parameters.

Right now, the most important active run parameters are `input_folder`, `script_file`, `output_file`, `artifact_subdir`, `analysis.*`, `planning.*`, `render.fps`, `models.transcription_model`, and `selection.max_reference_videos`. Some of the broader asset and model fields are already part of the skeleton, but are still future-facing.

## Core files

1. [run_parameters.yaml](/app/run_parameters.yaml) is the main per-run config.
2. [Scripts/sample1.json](/app/Scripts/sample1.json) is the current structured script example.
3. [pipeline/run_config.py](/app/pipeline/run_config.py) loads the YAML run config.
4. [pipeline/script_io.py](/app/pipeline/script_io.py) loads structured JSON scripts.

## Run it

Analyze a run:

```bash
python -m pipeline analyze --run-config /app/run_parameters.yaml
```

Generate a draft:

```bash
python -m pipeline generate --run-config /app/run_parameters.yaml
```

Shortcut:

```bash
python -m pipeline run --run-config /app/run_parameters.yaml
```

Inspect the resolved run config:

```bash
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
```

Because `run_parameters.yaml` defaults to the repo root, this also works:

```bash
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

## Structured scripts

The script format is now JSON-first. The current sample in [Scripts/sample1.json](/app/Scripts/sample1.json) includes:

1. top-level project metadata
2. global style metadata
3. a `scenes` list
4. scene-level timing
5. scene-level creative metadata such as `camera`, `mood`, `shot_type`, `text overlay`, and `preferred_asset_types`

Unknown scene fields are preserved in the generated shot plan, so the format is ready to grow with the project.

## Important notes

1. `.env` is ignored by Git.
2. `.env.example` is the tracked template.
3. `.dockerignore` excludes `.env`, `Video Input`, `Video Output`, and `artifacts`.
