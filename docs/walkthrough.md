# Pipeline Walkthrough

This is the practical guide for running the pipeline from the command line.

If you want the architecture and code-level explanation, use [tutorial.md](./tutorial.md).

One important truth up front: in this prototype, `train` does not fine-tune a generative model's weights. It prepares reusable style artifacts from your references so later generation can use them consistently.

Another important truth: the system now has an optional real generation stage through OpenAI image or video backends, but it is still not a full text-to-animation engine.

## What You Need To Know First

The pipeline expects three things:

1. an environment configuration in `.env`
2. a run definition in [`run_parameters.yaml`](../run_parameters.yaml)
3. a script file such as [`Scripts/sample1.json`](../Scripts/sample1.json)

The selected input bundle for a run is controlled by `input_folder`.

Current rule:

1. `reference_videos/` must contain at least one supported video
2. every other folder in the bundle is optional supporting input

The pipeline will also scan the whole selected bundle recursively for additional supporting videos, so empty optional folders do not break the run.

## The Main Commands

The CLI commands you will use most are:

```bash
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
python -m pipeline train --run-config /app/run_parameters.yaml
python -m pipeline generate --run-config /app/run_parameters.yaml
python -m pipeline run --run-config /app/run_parameters.yaml
```

What they do:

1. `show-run-config` resolves and prints the run configuration
2. `train` discovers videos, analyzes them, inventories assets, and writes reusable intermediate artifacts
3. `generate` loads those trained artifacts, builds continuity-aware prompts and shot metadata, and renders a draft video
4. `run` is a convenience command that runs `train` and then `generate`

## Step 1: Inspect The Current Run

Before changing anything, look at the current run definition:

```bash
sed -n '1,260p' /app/run_parameters.yaml
python -m json.tool /app/Scripts/sample1.json
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
```

What to check:

1. `input_folder`
2. `script_file`
3. `output_file`
4. `artifact_subdir`
5. `voiceover_file`
6. `analysis_video_subfolders`
7. `analysis.sample_frames`
8. `planning.honor_script_timing`
9. `render.fps`
10. `generation.backend`
11. `models.image_generation_model`
12. `models.video_generation_model`

## Step 2: Inspect The Input Bundle

Look at the selected project bundle:

```bash
find "/app/Video Input/Blonde Blazer Romance" -maxdepth 3 -type d | sort
find "/app/Video Input/Blonde Blazer Romance" -maxdepth 3 -type f | sort
sed -n '1,220p' "/app/Video Input/Blonde Blazer Romance/README.md"
```

For a healthy run, make sure:

1. `reference_videos/` contains at least one `.mp4`, `.mov`, `.mkv`, `.webm`, or another supported video format
2. the script matches the type of content you actually placed in the bundle
3. optional folders such as `closeups/videos` or `broll/videos` are present only if useful

## Step 3: Decide How You Want To Create Content

You have a few practical options for authoring a run.

### Option A: Minimal Video-Only Run

Provide:

1. one or more videos in `reference_videos/`
2. a script in `Scripts/`

This is the minimum required setup.

### Option B: Stronger Video Reference Run

Provide:

1. videos in `reference_videos/`
2. optional extra clips in `closeups/videos/`
3. optional inserts in `broll/videos/`
4. optional talking-head or social proof clips in `testimonials/videos/`

This gives the analysis stage more style material to work from.

### Option C: Broader Creative Project Bundle

Provide the video inputs above plus optional supporting assets such as:

1. `closeups/images/`
2. `broll/images/`
3. `portraits/`
4. `product_shots/`
5. `style_references/`
6. `brand_assets/`
7. `overlays/`
8. `audio/voiceovers/`

Some of these are not fully used by the current renderer yet, but they are good project structure for future stages and for keeping the bundle organized.

### Option D: Script-First Iteration

If the creative work is still evolving, focus first on:

1. editing `run_parameters.yaml`
2. editing `Scripts/sample1.json`
3. keeping one solid video in `reference_videos/`

This is a good way to iterate quickly on pacing, overlay text, and scene structure.

## Step 4: Edit The Script

The preferred script format is JSON.

Inspect the current sample:

```bash
python -m json.tool /app/Scripts/sample1.json
```

Typical scene fields:

1. `name`
2. `description`
3. `time start`
4. `time end`
5. `duration`
6. `text overlay`
7. `transition`
8. `camera`
9. `shot_type`
10. `mood`
11. `preferred_asset_types`
12. `notes`

Good uses for the script:

1. define scene order
2. define scene timing
3. define overlay copy
4. preserve creative metadata for planning

Useful reminder:

1. `description` becomes the narration basis
2. `duration` is used directly when `planning.honor_script_timing: true`
3. `text overlay` becomes the rendered on-screen copy
4. extra fields are preserved as metadata

## Step 5: Train First

Run the training stage before generation:

```bash
python -m pipeline train --run-config /app/run_parameters.yaml
```

This command:

1. validates the required reference videos
2. discovers supporting videos
3. analyzes style and audio
4. inventories available assets in the bundle
5. writes reusable intermediate artifacts for generation

Artifacts to inspect:

```bash
find /app/artifacts/sample1 -maxdepth 3 -type f | sort
python -m json.tool /app/artifacts/sample1/resolved_run_config.json | sed -n '1,220p'
python -m json.tool /app/artifacts/sample1/video_analyses.json | sed -n '1,220p'
python -m json.tool /app/artifacts/sample1/style_profile.json | sed -n '1,220p'
python -m json.tool /app/artifacts/sample1/asset_inventory.json | sed -n '1,220p'
find /app/artifacts/sample1/frames -maxdepth 2 -type f | sort
```

What to look for:

1. the right input bundle paths
2. the correct required video source
3. useful sample frames
4. plausible brightness, motion, and palette values
5. asset inventory entries that match the files you actually want the system to use
6. transcription behavior that matches your expectation

## Step 6: Run The Full Generate Flow

Once the training output looks reasonable, run:

```bash
python -m pipeline generate --run-config /app/run_parameters.yaml
```

This command:

1. loads the trained style profile from `artifacts/<artifact_subdir>/style_profile.json`
2. loads the trained asset inventory from `artifacts/<artifact_subdir>/asset_inventory.json`
3. loads the script
4. creates a continuity profile and motion-aware shot plan
5. optionally synthesizes shot assets through the configured generation backend
6. renders a draft video that prefers generated assets first and source-video excerpts second

Inspect the outputs:

```bash
python -m json.tool /app/artifacts/sample1/generated_assets.json | sed -n '1,220p'
python -m json.tool /app/artifacts/sample1/continuity_profile.json | sed -n '1,220p'
python -m json.tool /app/artifacts/sample1/shot_plan.json | sed -n '1,260p'
ls -lh "/app/Video Output"
```

If `ffprobe` is available:

```bash
ffprobe "/app/Video Output/sample1_draft.mp4"
```

If `generate` fails before rendering, the most common cause is that `train` has not been run yet for the same `artifact_subdir`.

What to look for in `shot_plan.json` now:

1. `source_asset_path`
2. `source_asset_type`
3. `media_kind`
4. `clip_start_s`
5. `motion_strategy`
6. `continuity_notes`
7. `generation_prompt`

If you turned on a real generation backend, also inspect:

1. `generated_assets.json`
2. the files inside `artifacts/<artifact_subdir>/generated_assets/`

## Step 6A: Turn On A Real Generation Backend

If you want the pipeline to create new shot assets instead of only reusing existing footage, configure a generation backend in [`run_parameters.yaml`](../run_parameters.yaml).

Image generation:

```yaml
generation:
  backend: openai_image
  use_reference_input: true

models:
  image_generation_model: gpt-image-1
```

Video generation:

```yaml
generation:
  backend: openai_video
  use_reference_input: true
  allow_fallback_to_draft: true

models:
  video_generation_model: sora-2
```

What you need for this to work:

1. `OPENAI_API_KEY` in `.env`
2. access to the configured model
3. the understanding that per-shot generation can be slower and more expensive than the draft compositor

## Step 7: Override Things From The CLI

You do not always need to edit YAML first. You can override a few important paths directly.

### Override The Source Path

```bash
python -m pipeline train \
  --run-config /app/run_parameters.yaml \
  --source "/app/Video Input/Blonde Blazer Romance/reference_videos"
```

Use this when you want to test a different source quickly.

### Override The Script File

```bash
python -m pipeline generate \
  --run-config /app/run_parameters.yaml \
  --script-file /app/Scripts/sample1.json
```

### Override The Output Video Path

```bash
python -m pipeline generate \
  --run-config /app/run_parameters.yaml \
  --output /app/Video\ Output/test_render.mp4
```

### Override The Artifact Directory

```bash
python -m pipeline train \
  --run-config /app/run_parameters.yaml \
  --project-dir /app/artifacts/session
```

## Step 8: A Good Iteration Loop

A solid working loop for day-to-day iteration is:

1. adjust the bundle contents
2. update `run_parameters.yaml`
3. update the script
4. inspect the resolved config
5. run `train`
6. inspect the artifacts
7. run `generate`
8. inspect the draft video

Concrete command sequence:

```bash
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
python -m json.tool /app/Scripts/sample1.json
python -m pipeline train --run-config /app/run_parameters.yaml
python -m json.tool /app/artifacts/sample1/style_profile.json | sed -n '1,220p'
python -m json.tool /app/artifacts/sample1/asset_inventory.json | sed -n '1,220p'
python -m pipeline generate --run-config /app/run_parameters.yaml
python -m json.tool /app/artifacts/sample1/generated_assets.json | sed -n '1,220p'
python -m json.tool /app/artifacts/sample1/continuity_profile.json | sed -n '1,220p'
python -m json.tool /app/artifacts/sample1/shot_plan.json | sed -n '1,260p'
ls -lh "/app/Video Output"
```

## Step 9: Common Adjustments You Will Probably Make

### Change The Project Bundle

Edit `input_folder` in [`run_parameters.yaml`](../run_parameters.yaml).

### Change The Script

Edit `script_file` in the YAML or use `--script-file`.

### Change The Draft Filename

Edit `output_file` in the YAML or use `--output`.

### Add Voiceover

Put a file in `audio/voiceovers/` and set `voiceover_file` in the YAML.

### Limit The Number Of Reference Videos

Set `selection.max_reference_videos` in the YAML.

### Adjust Analysis Density

Tune:

1. `analysis.sample_frames`
2. `analysis.timeline_scan_points`
3. `analysis.transcription_max_seconds`
4. `analysis.audio_analysis_max_seconds`

### Adjust Planning Feel

Tune:

1. `planning.honor_script_timing`
2. `planning.shot_duration_min_s`
3. `planning.shot_duration_max_s`
4. `planning.fallback_transition`

### Prepare Better Motion Inputs

If you want visibly stronger results, improve the bundle itself:

1. add multiple reference videos with different shot sizes and movement types
2. add closeup and b-roll clips that actually match the scenes in the script
3. keep the same subject, wardrobe, and lighting across those clips
4. use structured scene metadata like `subject`, `wardrobe`, `mood`, and `preferred_asset_types`

### Turn On Generated Assets

Tune:

1. `generation.backend`
2. `generation.use_reference_input`
3. `generation.allow_fallback_to_draft`
4. `models.image_generation_model`
5. `models.video_generation_model`

## Step 10: Troubleshooting

### Error: required video missing

Cause:

`reference_videos/` is empty or missing.

Fix:

Add at least one supported video file there.

### Error: wrong script path

Cause:

`script_file` points to the wrong file.

Fix:

Verify the file in `Scripts/` or use an absolute path.

### Analysis output looks weak

Possible causes:

1. the source video has low variety
2. the selected bundle has only one narrow reference clip
3. transcription is disabled or has no API key

Fixes:

1. add stronger reference material
2. add supporting video pools
3. inspect `style_profile.json` and sampled frames before generating again

### The output looks like panned still images

Cause:

The system falls back to still-image treatment when it cannot find or use a good video asset for the scene, or when `generation.backend` is still set to `draft_compositor`. It is also still not a full long-form animation model.

What that means:

1. the system is learning style signals and selecting source motion, not inventing full animation from scratch
2. `train` prepares the style profile and asset inventory, but it does not produce new motion by itself
3. if you do not enable `openai_image` or `openai_video`, the pipeline will stay in draft-compositor mode
4. even with `openai_video`, the result quality still depends on prompt quality, model access, and reference inputs

Fixes:

1. add more actual moving footage to the bundle
2. make `preferred_asset_types` point at video pools that really exist
3. inspect `shot_plan.json` and confirm the selected `media_kind` is `video` where you expect motion
4. turn on `generation.backend: openai_video` if you want the pipeline to request newly generated motion
5. inspect `generated_assets.json` and confirm shots were actually generated instead of falling back

### Draft video is structurally correct but visually simple

That is still expected to some degree. Even with generated assets enabled, the repo is still assembling per-shot clips into a draft rather than running a full filmmaking stack with character control, layout control, and high-end temporal supervision.

## Step 11: When To Read The Deep Tutorial

Use [tutorial.md](./tutorial.md) when you need to understand:

1. why the pipeline resolves paths the way it does
2. how discovery merges required and optional videos
3. how timing is derived from the script
4. how the dataclasses move between stages
5. how to change the code safely

## Short Version

If you only need the shortest useful run sequence, it is this:

```bash
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
python -m pipeline train --run-config /app/run_parameters.yaml
python -m pipeline generate --run-config /app/run_parameters.yaml
python -m json.tool /app/artifacts/sample1/generated_assets.json | sed -n '1,120p'
ls -lh "/app/Video Output"
```

If that works, then you can start refining the bundle, the YAML, and the JSON script.
