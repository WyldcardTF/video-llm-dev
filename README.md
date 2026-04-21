# video-llm-dev

This repo is a prototype pipeline for turning a project bundle plus a structured script into a generated draft video.

The important workflow split is:

1. `train` scans the selected project in `/app/Input`, analyzes required/supporting reference videos, and writes reusable artifacts.
2. `generate` loads those artifacts, builds a shot plan from the script, calls a selected full video-generation provider, and assembles the generated clips.

There is no local panning/image-only generation mode. Output clips must come from a real video-generation backend.

## Current Layout

The sample project lives here:

`/app/Input/Blonde Blazer Romance`

Key folders:

1. `Scripts/sample1.json` is the structured scene script.
2. `Supporting Data/general_assets/video/` is the required primary video-reference pool.
3. `Supporting Data/general_assets/images/` contains optional scene image references.
4. The rest of `Supporting Data/` is optional supporting media: closeups, b-roll, portraits, product shots, brand assets, audio, docs, and overlays.

## Model Choices

Choose a provider/model with `models.video_generation_model` in [run_parameters.yaml](/app/run_parameters.yaml). Leave `generation.backend: auto` unless you want to force a provider.

Useful presets:

1. `kling_2_5_turbo` is the cheapest scratchpad option if your Kling account exposes it.
2. `kling_2_6_std` is the default cheap Kling multi-image preset: silent, 5 seconds, 540p.
3. `veo_3_1_lite` is a lower-cost Google Veo prompt-testing preset.
4. `veo_3_1_fast` is a faster Veo 3.1 preset with image-reference support.
5. `kling_2_6_pro` is a stronger Kling 2.6 preset.
6. `sora_2` is the OpenAI frontier baseline.
7. `veo_3_1_quality` is a stronger Veo 3.1 pass.
8. `sora_2_pro` is the expensive final-quality OpenAI option.

List available presets:

```bash
python -m pipeline video-models
```

## Provider Secrets

Set the relevant key in `.env`:

```bash
OPENAI_API_KEY=...
GOOGLE_VERTEX_PROJECT=...
GOOGLE_VERTEX_LOCATION=us-central1
KLING_API_KEY=...
KLING_BASE_URL=https://api.klingapi.com
```

Google Veo uses Vertex AI credentials. If `GOOGLE_VERTEX_ACCESS_TOKEN` is blank, the pipeline tries Application Default Credentials and then `gcloud auth print-access-token`.

The default Kling flow uses `POST /v1/videos/multi-image2video` and sends local scene images as base64, so you do not need public image hosting for first tests.

## Run It

Inspect the resolved config:

```bash
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
```

Train:

```bash
python -m pipeline train --run-config /app/run_parameters.yaml
```

Generate:

```bash
python -m pipeline generate --run-config /app/run_parameters.yaml
```

Run both:

```bash
python -m pipeline run --run-config /app/run_parameters.yaml
```

## Scene References

Scripts can now attach explicit supporting files to each scene:

```json
{
  "path": "Supporting Data/general_assets/images/Scene 1/1.png",
  "role": "character",
  "label": "lead talent face reference",
  "prompt_hint": "Preserve facial proportions, blonde styling, and premium beauty framing.",
  "provider_use": "reference_input"
}
```

The model does not magically know why an image matters. The pipeline sends the image when the provider supports it, and it also writes the `role`, `label`, and `prompt_hint` into the prompt so the model has semantic instructions.

For the deep guide, read [docs/tutorial.md](/app/docs/tutorial.md). For the practical command-line runbook, read [docs/walkthrough.md](/app/docs/walkthrough.md).
