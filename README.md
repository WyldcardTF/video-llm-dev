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

## Run it

Analyze source videos:

```bash
python -m pipeline analyze --source path/to/reference_videos --project-dir artifacts/demo
```

Generate a draft video from a script:

```bash
python -m pipeline generate \
  --source path/to/reference_videos \
  --script-file path/to/script.txt \
  --project-dir artifacts/demo
```

If you want optional transcription-based voice notes, set `OPENAI_API_KEY` and add `--transcribe-voice`.
