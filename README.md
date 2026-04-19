# video-llm-dev

The goal is to create an app that can import reference videos and then, from a user-provided script, generate a new draft video in a similar style.

## Current prototype

The repo now includes a first-pass `pipeline/` package that does four things:

1. Ingest one video or a folder of videos.
2. Analyze visual style signals like pacing, motion, brightness, and palette.
3. Analyze the audio track for voice energy and pacing, with optional OpenAI transcription.
4. Turn a script into a shot plan and render a draft `.mp4` using sampled reference frames.

This is a prototype, so the output is a style-matched draft rather than a fully generative video model.

For a step-by-step explanation of the code and how to evolve it, see `docs/tutorial.md`.

## Environment configuration

The repo now reads runtime configuration from `.env`.

1. Edit `.env` for your local paths, file names, OpenAI settings, and pipeline defaults.
2. `docker-compose.yaml` injects that file into the container with `env_file`.
3. The Python app also loads `.env` directly through `python-dotenv`, so the same settings work locally and in Docker.

Important:

1. `.env` is ignored by Git.
2. `.env.example` is the tracked template.
3. `.dockerignore` excludes `.env` so secrets are not baked into the image.

## Run it

Analyze source videos:

```bash
python -m pipeline analyze
```

Generate a draft video from a script:

```bash
python -m pipeline generate
```

Those commands now use `.env` defaults such as `VIDEO_INPUT_DIR`, `SCRIPT_INPUT_FILE`, `PIPELINE_PROJECT_DIR`, and `VIDEO_OUTPUT_DIR`.

You can still override any of them on the command line, for example:

```bash
python -m pipeline generate \
  --source /app/my-reference-videos \
  --script-file /app/my-reference-videos/custom-script.txt \
  --output /app/Video\ Output/custom-draft.mp4
```
