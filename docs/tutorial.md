# Pipeline Tutorial

This tutorial explains the current prototype and gives you concrete commands to run at every step.

The key idea is:

1. `.env` defines environment roots and secrets.
2. `run_parameters.yaml` defines one specific model run.
3. `Scripts/sample1.json` defines the scenes for that run.

## 1. Mental model

The pipeline currently works like this:

1. select one input bundle with `input_folder`
2. find reference videos inside that bundle
3. analyze the videos to extract style signals
4. load a structured script
5. convert that script into a shot plan
6. render a draft video

Think of it as:

`input bundle -> analysis -> style profile -> shot plan -> draft video`

## 2. Understand the config split

## `.env`

Use `.env` for:

1. environment paths
2. folder roots
3. stable artifact names
4. secrets like `OPENAI_API_KEY`

Inspect it:

```bash
sed -n '1,220p' /app/.env
```

## `run_parameters.yaml`

Use `run_parameters.yaml` for:

1. `input_folder`
2. `script_file`
3. `output_file`
4. `artifact_subdir`
5. analysis settings
6. planning settings
7. render settings
8. model-run settings
9. asset subfolder definitions

Inspect it:

```bash
sed -n '1,260p' /app/run_parameters.yaml
```

## `Scripts/sample1.json`

Use the structured script for scene-level control.

Inspect it:

```bash
python -m json.tool /app/Scripts/sample1.json
```

## 3. Inspect the current bundle structure

The current run selects the subfolder:

`/app/Video Input/Blonde Blazer Romance`

Inspect the skeleton:

```bash
find "/app/Video Input/Blonde Blazer Romance" -maxdepth 3 -type d | sort
sed -n '1,220p' "/app/Video Input/Blonde Blazer Romance/README.md"
```

This bundle now includes folders such as:

1. `reference_videos`
2. `closeups/videos`
3. `closeups/images`
4. `broll/videos`
5. `broll/images`
6. `testimonials/videos`
7. `portraits`
8. `product_shots`
9. `3d_models`
10. `style_references`
11. `brand_assets`
12. `overlays`
13. `audio/voiceovers`
14. `audio/music`
15. `audio/sfx`
16. `docs/storyboards`
17. `docs/transcripts`

Some of these are not yet consumed directly by the renderer, but they are important parts of a realistic project skeleton.

## 4. Learn the CLI first

Inspect the CLI:

```bash
python -m pipeline --help
python -m pipeline analyze --help
python -m pipeline generate --help
python -m pipeline run --help
python -m pipeline show-run-config --help
```

Read the implementation:

```bash
sed -n '1,260p' /app/pipeline/cli.py
```

The important change is that the CLI is now YAML-driven.

## 5. Inspect the resolved run config

Before running anything, inspect what the YAML means after it is loaded:

```bash
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
```

Read the loader:

```bash
sed -n '1,320p' /app/pipeline/run_config.py
```

Pay attention to:

1. `input_folder`
2. `analysis_video_subfolders`
3. `asset_subfolders`
4. `analysis`
5. `planning`
6. `render`
7. `models`

Which fields are already active today:

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
11. `selection.max_reference_videos`
12. `workflow.save_resolved_run_config`

Which fields are mostly future-facing skeleton fields right now:

1. most entries in `asset_subfolders`
2. `render.output_width`
3. `render.output_height`
4. `models.image_generation_model`
5. `models.video_generation_model`
6. `models.voice_generation_model`
7. `selection.require_videos`
8. `selection.allow_images_as_fallback`
9. `workflow.reuse_existing_analysis`

Those future-facing fields are still useful because they define the project shape we expect to grow into.

## 6. Understand how scripts are loaded

The new script loader supports:

1. structured JSON scene files
2. plain text fallback scripts

Read it:

```bash
sed -n '1,320p' /app/pipeline/script_io.py
```

The current `sample1.json` now has:

1. top-level project metadata
2. top-level global style metadata
3. a `scenes` list
4. scene-level timing
5. scene-level creative fields

The loader preserves extra fields, so you can keep expanding the script format.

## 7. Understand the data models

Read the models:

```bash
sed -n '1,260p' /app/pipeline/models.py
```

Important objects:

1. `VideoAnalysis`
2. `StyleProfile`
3. `ScriptScene`
4. `ScriptDocument`
5. `ShotPlanItem`
6. `GenerationPlan`

These are the handoff objects between stages.

## 8. Run analysis

Run the analysis stage:

```bash
python -m pipeline analyze --run-config /app/run_parameters.yaml
```

What this does:

1. loads `run_parameters.yaml`
2. resolves `input_folder`
3. searches the configured analysis subfolders for videos
4. analyzes the discovered videos
5. writes artifacts under the configured artifact folder

Read the analyzer:

```bash
sed -n '1,320p' /app/pipeline/analyze.py
```

Inspect the output:

```bash
find /app/artifacts -maxdepth 3 -type f | sort
python -m json.tool /app/artifacts/sample1/resolved_run_config.json | sed -n '1,260p'
python -m json.tool /app/artifacts/sample1/video_analyses.json | sed -n '1,220p'
python -m json.tool /app/artifacts/sample1/style_profile.json | sed -n '1,220p'
find /app/artifacts/sample1/frames -maxdepth 2 -type f | sort
```

Questions to ask:

1. Did it find the right videos?
2. Does the style profile feel plausible?
3. Are the sampled frames useful?
4. Did transcription run the way you expected?

## 9. Understand style aggregation

Read the style aggregation code:

```bash
sed -n '1,220p' /app/pipeline/style.py
```

This stage turns many `VideoAnalysis` objects into one `StyleProfile`.

Inspect the style profile again:

```bash
python -m json.tool /app/artifacts/sample1/style_profile.json | sed -n '1,220p'
```

## 10. Understand planning

Read the planner:

```bash
sed -n '1,260p' /app/pipeline/planning.py
```

Notice the important new behavior:

1. JSON scene timing can be honored directly
2. fallback duration logic still exists
3. scene metadata can be included in planning notes
4. transition fallback comes from `run_parameters.yaml`

That means the YAML and JSON now work together:

1. YAML controls run-level planning rules
2. JSON controls scene-level creative details

## 11. Generate a draft

Run the full generate flow:

```bash
python -m pipeline generate --run-config /app/run_parameters.yaml
```

This will:

1. analyze the selected inputs
2. load `Scripts/sample1.json`
3. create `shot_plan.json`
4. render a draft video

Inspect the outputs:

```bash
python -m json.tool /app/artifacts/sample1/shot_plan.json | sed -n '1,260p'
ls -lh "/app/Video Output"
```

If `ffprobe` is available:

```bash
ffprobe "/app/Video Output/sample1_draft.mp4"
```

## 12. Understand rendering

Read the renderer:

```bash
sed -n '1,260p' /app/pipeline/render.py
```

The current renderer still uses a simple draft strategy:

1. choose a reference image
2. resize it to the output frame
3. apply slow motion
4. draw overlay text
5. write the video

This is intentionally modest. It is here to prove that the earlier stages produce enough structure to drive output.

## 13. How the new JSON script is used

The current `sample1.json` includes fields like:

1. `name`
2. `description`
3. `time start`
4. `time end`
5. `duration`
6. `camera`
7. `shot_type`
8. `mood`
9. `text overlay`
10. `preferred_asset_types`
11. `notes`

Right now the pipeline uses them like this:

1. `description` drives the shot narration
2. `duration` is used directly when `honor_script_timing: true`
3. `text overlay` becomes the rendered on-screen text
4. `transition` becomes the shot transition when present
5. unknown fields are preserved inside `scene_metadata`
6. `scene_metadata` is folded into planning notes when enabled

That means you can safely add more fields without losing them.

## 14. A good working routine

When iterating on a project, a good loop is:

1. update `run_parameters.yaml`
2. update `Scripts/sample1.json`
3. place assets inside the selected `input_folder`
4. run `python -m pipeline analyze --run-config /app/run_parameters.yaml`
5. inspect the JSON artifacts
6. run `python -m pipeline generate --run-config /app/run_parameters.yaml`
7. inspect the rendered draft

Concrete command sequence:

```bash
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
python -m json.tool /app/Scripts/sample1.json
python -m pipeline analyze --run-config /app/run_parameters.yaml
python -m json.tool /app/artifacts/sample1/style_profile.json | sed -n '1,200p'
python -m pipeline generate --run-config /app/run_parameters.yaml
python -m json.tool /app/artifacts/sample1/shot_plan.json | sed -n '1,260p'
ls -lh "/app/Video Output"
```

## 15. What to improve next

The highest-value next improvements are:

1. reuse existing analysis instead of recomputing every time
2. use asset pools like `closeup_images`, `product_shots`, and `three_d_models` directly in rendering
3. introduce real prompt generation from scene metadata
4. add stronger shot detection instead of simple motion heuristics
5. align shots to real voiceover timing
6. add tests for YAML loading, JSON scene parsing, and CLI runs

## 16. Suggested next session

A strong next step would be one of these:

1. expand the `sample1.json` schema together
2. make the renderer choose from the new asset pools intentionally
3. add analysis caching with `reuse_existing_analysis`
4. walk through one generated `shot_plan.json` line by line
