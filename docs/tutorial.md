# Pipeline Tutorial

This document is a guided walkthrough of the current prototype in `pipeline/`.

The goal is not only to show how to run the code, but also to explain what each module is doing, what assumptions it makes, and what would need to change to turn this into a stronger app.

## 1. What this prototype actually does

Right now, the code does this:

1. Finds one or more reference videos on disk.
2. Samples frames from those videos.
3. Estimates simple style signals such as brightness, motion, pacing, color palette, and voice characteristics.
4. Combines those signals into a `StyleProfile`.
5. Splits a script into beats and turns them into a `GenerationPlan`.
6. Renders a draft video by reusing sampled reference frames as backgrounds and overlaying text.

That means this is a style-analysis and draft-rendering pipeline.

It is not yet a full generative video system. It does not currently:

1. Generate brand-new scenes with an image or video model.
2. Clone a speaker's voice.
3. Lip-sync an avatar.
4. Understand story structure in a deep semantic way.
5. Learn style from examples with a trained model.

This distinction matters because it tells us what the code is good for today:

1. Understanding the pipeline shape.
2. Producing inspectable intermediate outputs.
3. Giving us a base we can refine step by step.

## 2. The mental model

It helps to think of the pipeline as four stages:

1. `reference videos -> measurements`
2. `measurements -> style profile`
3. `script -> shot plan`
4. `shot plan + style profile -> draft video`

That is the big picture.

If you keep that model in mind, the individual files become much easier to understand.

## 3. Configure `.env` first

Before running the commands, open `.env`.

That file now controls the main runtime parameters, including:

1. OpenAI secrets and model names.
2. The video input folder.
3. The video output folder.
4. The script file path.
5. The project artifacts folder.
6. Sampling, timing, and render defaults.

The most important variables are:

1. `VIDEO_INPUT_DIR`
2. `SCRIPT_INPUT_FILE`
3. `VIDEO_OUTPUT_DIR`
4. `PIPELINE_PROJECT_DIR`
5. `OPENAI_API_KEY`

The code loads `.env` directly, and Docker Compose also injects the same file into the container.

### What to run now

Start by checking the current configuration and making sure the default folders exist:

```bash
sed -n '1,220p' .env
mkdir -p "/app/Video Input" "/app/Video Output" "/app/artifacts/session"
ls -la "/app/Video Input"
ls -la "/app/Video Output"
```

If you do not already have a script file, create a tiny one:

```bash
cat > "/app/Video Input/script.txt" <<'EOF'
Open on a strong visual hook.
Show the main subject in motion.
Explain the key idea clearly.
Close with a short call to action.
EOF
```

If you want to verify what the app thinks the active defaults are, run:

```bash
python -c "from pipeline.config import get_settings; print(get_settings())"
```

## 4. How to run it

## Analyze only

Use this when you want to inspect how the code interprets your reference videos.

```bash
python -m pipeline analyze
```

This creates files such as:

1. `PIPELINE_PROJECT_DIR/VIDEO_ANALYSES_FILENAME`
2. `PIPELINE_PROJECT_DIR/STYLE_PROFILE_FILENAME`
3. `PIPELINE_PROJECT_DIR/FRAMES_DIR_NAME/...`

## Generate a draft video

Use this when you also have a script file.

```bash
python -m pipeline generate
```

This adds:

1. `PIPELINE_PROJECT_DIR/SHOT_PLAN_FILENAME`
2. `VIDEO_OUTPUT_DIR/OUTPUT_FILENAME`

## Optional transcription

If you set `OPENAI_API_KEY`, you can also ask the code to transcribe part of the audio:

```bash
python -m pipeline analyze --transcribe-voice
```

That transcription is used only to improve the voice-style description. It is not yet used to create new audio.

You can still override anything on the command line:

```bash
python -m pipeline generate \
  --source /app/my-reference-videos \
  --script-file /app/my-reference-videos/script.txt \
  --output custom-draft.mp4
```

In that example, `custom-draft.mp4` will still be written inside `VIDEO_OUTPUT_DIR` because it is a relative output path.

## 5. What each file is responsible for

Here is the map of the package:

1. `pipeline/cli.py`
   The command-line entrypoint.
2. `pipeline/ingest.py`
   Finds video files.
3. `pipeline/analyze.py`
   Reads the video and extracts measurements.
4. `pipeline/voice.py`
   Describes the voice and optionally transcribes audio.
5. `pipeline/style.py`
   Combines per-video measurements into one style profile.
6. `pipeline/planning.py`
   Turns a script into a sequence of shots.
7. `pipeline/render.py`
   Builds the draft video file.
8. `pipeline/models.py`
   Defines the data structures passed between stages.
9. `pipeline/io_utils.py`
   Small helpers for file IO and JSON export.

The easiest way to understand the project is to read those files in that order.

## 6. Step-by-step walkthrough

## Step 1: CLI entrypoint

Start with `pipeline/cli.py`.

This file is where the user-facing commands live:

1. `analyze`
2. `generate`
3. `run`

### What to run now

Start by discovering the available commands and their options:

```bash
python -m pipeline --help
python -m pipeline analyze --help
python -m pipeline generate --help
python -m pipeline run --help
```

If you want to inspect the CLI source while reading the help output:

```bash
sed -n '1,220p' /app/pipeline/cli.py
```

### `analyze`

The `analyze` command does this:

1. Makes sure the output directory exists.
2. Finds videos using `discover_video_files`.
3. Creates a `VideoAnalyzer`.
4. Runs analysis on each video.
5. Builds one combined `StyleProfile`.
6. Writes JSON outputs to disk.

This command is useful because it separates style extraction from generation.

### `generate`

The `generate` command repeats the analysis and then adds three more steps:

1. Reads the script text file.
2. Converts the script into a `GenerationPlan`.
3. Renders the final draft video.

### `run`

This is just a convenience wrapper that calls `generate` with a default output path.

## Step 2: Ingestion

`pipeline/ingest.py` is intentionally small.

Its job is to answer one question:

Which video files should the pipeline operate on?

`discover_video_files(source)` accepts either:

1. A single video file.
2. A directory containing videos.

It validates the source, filters by extension, and returns a list of `Path` objects.

This is the first step because every later stage depends on having a clean list of source assets.

### What to run now

First, confirm that your input folder actually contains video files:

```bash
find "/app/Video Input" -maxdepth 2 -type f
```

If you want to inspect the ingestion code:

```bash
sed -n '1,200p' /app/pipeline/ingest.py
```

Then run the first real pipeline command:

```bash
python -m pipeline analyze
```

If you want to point at a different folder manually:

```bash
python -m pipeline analyze --source /app/my-other-video-folder
```

## Step 3: Data models

`pipeline/models.py` defines the data that moves between stages.

This is important because good pipelines are easier to reason about when each stage has a clear input and output.

### `FrameSample`

Represents one saved frame from a video.

Fields:

1. `timestamp_s`
2. `image_path`
3. `average_color`

### `AudioProfile`

Represents the simple audio measurements for one video.

Fields include:

1. Whether audio was detected.
2. Mean and peak level.
3. Silence ratio.
4. Optional transcript.
5. Human-readable voice description.

### `VideoAnalysis`

Represents the result of analyzing one source video.

It contains:

1. Video metadata such as duration, size, and fps.
2. Visual measurements like brightness, motion, and palette.
3. Saved sample frames.
4. The audio profile.

### `StyleProfile`

Represents the aggregated style learned from all reference videos.

It is the main handoff between analysis and generation.

### `ShotPlanItem` and `GenerationPlan`

These represent the script broken into individual beats and the full list of shots to render.

### What to run now

Inspect the data model definitions:

```bash
sed -n '1,240p' /app/pipeline/models.py
```

After running `analyze`, inspect the generated JSON structure:

```bash
python -m json.tool /app/artifacts/session/video_analyses.json | sed -n '1,200p'
python -m json.tool /app/artifacts/session/style_profile.json | sed -n '1,200p'
```

This lets you connect the Python dataclasses to the actual files being produced.

## Step 4: Video analysis

This is the heart of the current prototype.

Open `pipeline/analyze.py`.

The main class is `VideoAnalyzer`.

### `analyze_many`

This just loops over the list of video paths and calls `analyze_video` for each one.

### `analyze_video`

This is the main workflow for a single file:

1. Create IDs and output folders.
2. Open the video with OpenCV.
3. Read metadata such as fps, frame count, width, height, and duration.
4. Extract a handful of sample frames.
5. Estimate brightness.
6. Estimate motion and pacing.
7. Analyze the audio track.
8. Extract a rough color palette.
9. Return a `VideoAnalysis` object.

Each of those steps is intentionally simple and inspectable.

### `_extract_sample_frames`

This function samples frames at evenly spaced timestamps from about 5 percent to 95 percent of the video.

Why do that?

Because we want a broad overview of the video without reading every frame.

For each timestamp it:

1. Seeks to the frame.
2. Reads it.
3. Saves it as a `.jpg`.
4. Computes its average color.

This is useful for two later reasons:

1. The style profile can use the sample frames.
2. The renderer can reuse those images as reference backgrounds.

### `_estimate_brightness`

This function loads the saved sample frames, converts them to grayscale, and computes the average brightness.

This gives us one simple signal about the visual mood:

1. darker videos
2. brighter videos

It is very basic, but it is a helpful first feature.

### `_estimate_motion_and_pacing`

This function approximates how dynamic the edit is.

It samples points across the video timeline, converts frames to a smaller grayscale image, and measures the average pixel difference between consecutive frames.

That produces:

1. `motion_score`
   Roughly, how much the image changes over time.
2. `estimated_shot_length_s`
   An estimate of how quickly cuts happen.

Important note:

This is only a heuristic. It is not true shot detection. Big camera motion and big scene cuts can both look like "difference" to this method.

### `_extract_palette`

This function creates a rough color palette by:

1. Resizing each sample frame to `32x32`.
2. Flattening pixels.
3. Quantizing colors into coarse bins.
4. Counting the most common bins.

The result is a short list of dominant hex colors.

This is a lightweight way to get color direction without using a heavier clustering algorithm.

### `_analyze_audio`

This function uses `ffmpeg` to extract raw mono audio and then computes:

1. `mean_level`
2. `peak_level`
3. `silence_ratio`

Those numbers are fed into `describe_voice_style` in `pipeline/voice.py`.

If `transcribe_voice=True`, it can also call the OpenAI transcription API.

This is still a rough sketch of voice style, not speaker modeling.

### What to run now

Run analysis again if needed:

```bash
python -m pipeline analyze
```

Inspect the saved analysis artifacts:

```bash
python -m json.tool /app/artifacts/session/video_analyses.json | sed -n '1,220p'
find /app/artifacts/session/frames -maxdepth 2 -type f | sort
```

If you want to read the analyzer source while comparing it with the JSON:

```bash
sed -n '1,260p' /app/pipeline/analyze.py
```

A good habit here is:

1. look at one sampled frame
2. look at its JSON entry
3. check whether the brightness, palette, and pacing seem believable

## Step 5: Voice utilities

`pipeline/voice.py` has two jobs.

### `maybe_transcribe_video`

This extracts a short `.mp3` from the video with `ffmpeg` and sends it to the OpenAI transcription API when `OPENAI_API_KEY` is present.

That gives us words, but not a cloned voice.

### `describe_voice_style`

This converts simple signal measurements into labels such as:

1. `soft-spoken`
2. `balanced`
3. `energetic`
4. `measured`
5. `steady`
6. `fast-moving`

If a transcript exists, it also tries to describe the phrasing style.

This is deliberately heuristic and readable. That is good for learning, even though it is not yet sophisticated.

### What to run now

If your `.env` contains a valid `OPENAI_API_KEY`, try analysis with transcription enabled:

```bash
python -m pipeline analyze --transcribe-voice
```

Then inspect the audio fields:

```bash
python -m json.tool /app/artifacts/session/video_analyses.json | rg -n "voice_style|transcript|mean_level|peak_level|silence_ratio"
```

If you want to study the voice helper code:

```bash
sed -n '1,220p' /app/pipeline/voice.py
```

## Step 6: Style aggregation

`pipeline/style.py` takes multiple `VideoAnalysis` objects and merges them into one `StyleProfile`.

This is where the code moves from:

1. "what happened in each source video?"

to:

2. "what is the overall style we want to imitate?"

It does this by combining:

1. Most common resolution.
2. Average shot duration.
3. Average brightness.
4. Average motion.
5. Most common colors.
6. Voice descriptions.
7. All saved reference images.

It also converts the estimated shot duration into a rough pacing label:

1. `fast`
2. `medium`
3. `slow`

This file is where you would later make the style representation smarter.

### What to run now

Inspect the aggregated style profile:

```bash
python -m json.tool /app/artifacts/session/style_profile.json | sed -n '1,220p'
```

Then compare it to the aggregation code:

```bash
sed -n '1,220p' /app/pipeline/style.py
```

At this stage, ask:

1. Does the pacing label match the reference videos?
2. Do the dominant colors feel right?
3. Does the voice summary sound plausible?

## Step 7: Planning from a script

`pipeline/planning.py` converts a raw text script into a renderable shot plan.

### `_split_script`

This splits the script into segments.

It uses:

1. one line per shot if the script has multiple lines
2. sentence splitting otherwise

This is a simple but useful rule because it gives the user some control.

### `_estimate_duration`

This estimates shot duration from:

1. word count
2. the preferred duration found in the style profile
3. the fast or slow pacing label

This is not timing-aware narration yet. It is just a good first guess.

### `_build_visual_direction`

This creates a natural-language note describing what the shot should feel like.

Right now this note is not consumed by a generation model, but it is still valuable because:

1. it makes the plan human-readable
2. it can later become the prompt for an image or video model

### `_overlay_text`

This shortens the script segment so it can be displayed on screen in the prototype renderer.

### What to run now

First, inspect your script:

```bash
sed -n '1,120p' "/app/Video Input/script.txt"
```

Then generate the plan and the draft:

```bash
python -m pipeline generate
```

Now inspect the shot plan:

```bash
python -m json.tool /app/artifacts/session/shot_plan.json | sed -n '1,260p'
```

And compare it with the planner code:

```bash
sed -n '1,220p' /app/pipeline/planning.py
```

This is the moment to check whether:

1. each line or sentence became a sensible shot
2. the durations feel reasonable
3. the visual notes are useful

## Step 8: Rendering

`pipeline/render.py` turns the `GenerationPlan` into an actual video file.

This is the current rendering strategy:

1. Choose a reference image for each shot.
2. Resize it to fill the target frame.
3. Apply a slow zoom and pan effect.
4. Draw a text panel on top.
5. Write frames into an `.mp4`.
6. Optionally mux an external voiceover track.

### Why this renderer exists

The renderer is intentionally modest.

Its job is not to be impressive. Its job is to prove that the earlier stages produce enough structure to drive a generated output.

That makes it a very good teaching tool.

### `_load_background`

Uses the reference frame for the shot if one is available.

If not, it falls back to a solid color from the style palette.

### `_apply_motion`

Adds a subtle zoom and alternating pan direction.

This is a classic "Ken Burns" style move.

### `_draw_overlay`

Draws a rounded dark panel, a color accent bar, and the text overlay using Pillow.

### `_mux_audio_track`

If you provide a narration file, `ffmpeg` combines it with the silent rendered video.

### What to run now

Generate the draft video if you have not done it already:

```bash
python -m pipeline generate
```

Confirm the output exists:

```bash
ls -lh "/app/Video Output"
```

If `ffprobe` is available in your environment, inspect the generated file:

```bash
ffprobe "/app/Video Output/draft.mp4"
```

If you want to read the renderer code while looking at the output:

```bash
sed -n '1,260p' /app/pipeline/render.py
```

At this step, focus on three questions:

1. Does the video feel related to the references?
2. Is the pacing acceptable?
3. Is the text overlay readable?

## 7. What to inspect after a run

When you run the pipeline, do not jump straight to the final video.

The best way to understand and improve the system is to inspect the intermediate artifacts.

### `video_analyses.json`

Look here to answer:

1. Did the code read the video metadata correctly?
2. Do the motion and brightness values make sense?
3. Did the color palette feel right?
4. Did audio detection work?

Command:

```bash
python -m json.tool /app/artifacts/session/video_analyses.json | sed -n '1,220p'
```

### `style_profile.json`

Look here to answer:

1. Does the combined style summary feel true to the reference videos?
2. Is the pacing label believable?
3. Are the dominant colors reasonable?

Command:

```bash
python -m json.tool /app/artifacts/session/style_profile.json | sed -n '1,220p'
```

### `shot_plan.json`

Look here to answer:

1. Did the script split into sensible shots?
2. Are the durations okay?
3. Is the visual direction helpful?

Command:

```bash
python -m json.tool /app/artifacts/session/shot_plan.json | sed -n '1,260p'
```

### `frames/`

Look here to answer:

1. Did we sample useful reference frames?
2. Are these the kinds of frames we want the renderer to reuse?

Command:

```bash
find /app/artifacts/session/frames -maxdepth 2 -type f | sort
```

### `VIDEO_OUTPUT_DIR/OUTPUT_FILENAME`

Look here to answer:

1. Does the output visually feel related to the source?
2. Is the pacing okay?
3. Is the overlay text readable?

Command:

```bash
ls -lh "/app/Video Output"
```

## 8. What is still missing for a real app

To make an app like this truly work in production, we need more than heuristics and a local CLI.

There are four big capability gaps.

## A. Better style understanding

Right now style is inferred from:

1. brightness
2. motion
3. palette
4. rough voice measurements

A stronger system would also model:

1. shot types such as close-up, medium, wide
2. camera movement types
3. scene composition
4. subtitle style
5. music energy
6. editing rhythm
7. semantic themes

## B. Better generation

Right now the renderer reuses sampled images.

A stronger app would generate or transform visuals using:

1. image models for per-shot keyframes
2. video models for motion generation
3. editing templates
4. speech synthesis or voice cloning
5. caption styling

## C. Better planning

Right now the planner uses script lines and heuristics.

A stronger planner would:

1. detect scene changes in the script
2. assign shot types intentionally
3. time shots against actual voiceover duration
4. generate prompts per shot
5. maintain character and object consistency

## D. Better product architecture

A usable app would also need:

1. a web API or backend service
2. a queue for long video jobs
3. object storage for uploaded assets
4. a database for projects and runs
5. auth and user accounts
6. progress tracking
7. retries and failure handling
8. observability and logs

## 9. The most useful next improvements in this repo

If we want to improve this codebase gradually, these are the highest-value next steps.

## Improvement 1: Stop re-analyzing every time

Right now `generate` re-runs the analysis.

It would be better to:

1. save the analysis once
2. reload `style_profile.json` when it already exists

That would make iteration faster.

## Improvement 2: Add true shot detection

The current motion heuristic is useful, but it is not true cut detection.

A next step would be:

1. detect scene boundaries more explicitly
2. compute average shot length from real cuts

## Improvement 3: Add transcript-aware planning

Once the transcription exists, we can use it for more than just voice labels.

We could:

1. align timing to real speech
2. extract repeated phrases
3. detect hook and payoff structure

## Improvement 4: Introduce prompt generation

The `visual_direction` string is the start of a prompt system.

A strong next step would be:

1. produce a structured prompt per shot
2. include camera, mood, color, composition, and motion tags

## Improvement 5: Add tests

For a pipeline like this, tests matter a lot.

We should add:

1. unit tests for `discover_video_files`
2. unit tests for script splitting and duration estimation
3. fixture-based tests for style aggregation
4. smoke tests for the CLI

## Improvement 6: Separate analysis from rendering more cleanly

Over time, you will likely want these as distinct subsystems:

1. analysis service
2. planning service
3. generation service
4. rendering service

That separation makes production architecture easier later.

## 10. A good way to learn this code slowly

Here is a simple learning path.

### Pass 1: Understand inputs and outputs

Read:

1. `pipeline/cli.py`
2. `pipeline/models.py`

Goal:

Understand what goes in, what comes out, and what data objects connect the stages.

Commands:

```bash
sed -n '1,220p' /app/pipeline/cli.py
sed -n '1,240p' /app/pipeline/models.py
```

### Pass 2: Understand analysis

Read:

1. `pipeline/ingest.py`
2. `pipeline/analyze.py`
3. `pipeline/voice.py`

Goal:

Understand how raw video becomes measurable style data.

Commands:

```bash
sed -n '1,200p' /app/pipeline/ingest.py
sed -n '1,260p' /app/pipeline/analyze.py
sed -n '1,220p' /app/pipeline/voice.py
```

### Pass 3: Understand generation planning

Read:

1. `pipeline/style.py`
2. `pipeline/planning.py`

Goal:

Understand how the code turns measurements into decisions.

Commands:

```bash
sed -n '1,220p' /app/pipeline/style.py
sed -n '1,220p' /app/pipeline/planning.py
```

### Pass 4: Understand rendering

Read:

1. `pipeline/render.py`

Goal:

Understand how the final `.mp4` is assembled.

Commands:

```bash
sed -n '1,260p' /app/pipeline/render.py
```

### Pass 5: Run and inspect artifacts

Run the pipeline on a tiny example and compare:

1. the reference videos
2. `video_analyses.json`
3. `style_profile.json`
4. `shot_plan.json`
5. the rendered draft

This is where the code usually clicks.

Commands:

```bash
python -m pipeline analyze
python -m pipeline generate
python -m json.tool /app/artifacts/session/video_analyses.json | sed -n '1,160p'
python -m json.tool /app/artifacts/session/style_profile.json | sed -n '1,160p'
python -m json.tool /app/artifacts/session/shot_plan.json | sed -n '1,200p'
ls -lh "/app/Video Output"
```

## 11. A concrete practice exercise

A good next exercise is:

1. Pick 2 short reference videos with a clear style.
2. Create a 4-line script where each line is one intended shot.
3. Run `python -m pipeline generate`.
4. Open `shot_plan.json`.
5. Compare each shot to the rendered video.
6. Change one thing in the planner, such as duration logic.
7. Run it again and compare results.

Concrete command flow:

```bash
sed -n '1,120p' "/app/Video Input/script.txt"
python -m pipeline generate
python -m json.tool /app/artifacts/session/shot_plan.json | sed -n '1,220p'
ls -lh "/app/Video Output"
```

This will teach you more quickly than reading passively.

## 12. The honest summary

The code currently demonstrates the architecture of a style-matched video pipeline, not the final intelligence of one.

That is okay.

In fact, it is a good way to build this kind of app, because we first prove:

1. what the stages are
2. what data each stage needs
3. what artifacts we should inspect
4. where heuristics stop being enough

Once that is clear, the next iterations become much more focused.

## 13. Suggested next session

A very productive next step would be to do one of these together:

1. walk through `pipeline/analyze.py` line by line
2. run the pipeline on a tiny sample project and inspect the outputs
3. improve one specific stage, such as planning or rendering

Any of those would be a strong next move.
