# video-llm-dev

This repo turns a project bundle plus a structured script into a Kling-generated draft video.

The workflow is:

1. `train` scans the selected project in `/app/Input`, inventories images, analyzes active script video references when present, and writes reusable artifacts.
2. `generate` loads those artifacts, builds a shot plan from the script, calls Kling, and assembles generated clips.

There is no local panning/image-only generation mode. Output clips come from Kling.

## Layout

The sample project lives at `/app/Input/Blonde Blazer Romance`.

Key folders:

1. `Scripts/script1.json` is the structured scene script.
2. `Supporting Data/general_assets/images/` contains scene image references.
3. `Supporting Data/general_assets/video/` can hold optional style or motion references.
4. The rest of `Supporting Data/` is optional supporting media.

Inside any `Supporting Data` branch, a final folder named `general` gives whole-video context. A final folder named like `scene 1` gives scene-specific context.

## Kling Setup

Set Kling secrets in `.env`:

```bash
KLING_API_ACCESS_KEY=...
KLING_API_SECRET_KEY=...
KLING_BASE_URL=https://api-singapore.klingai.com
```

Choose a Kling preset in [run_parameters.yaml](/app/run_parameters.yaml):

```yaml
models:
  video_generation_model: kling_2_6_std
```

Useful presets:

1. `kling_2_5_turbo`
2. `kling_2_6_std`
3. `kling_2_6_pro`
4. `kling_2_6_pro_audio`

## Run It

```bash
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
python -m pipeline train --run-config /app/run_parameters.yaml
python -m pipeline generate --run-config /app/run_parameters.yaml
```

Final renders are progressive. With `output_file: script1_draft.mp4`, the CLI writes `script1_draft_1.mp4`, then `script1_draft_2.mp4`, and so on.

## Scene References

Scripts attach supporting files to each scene:

```json
{
  "path": "Supporting Data/general_assets/images/scene 1/1.png",
  "use_asset": true,
  "asset_type": "image",
  "role": "character",
  "label": "lead talent face reference",
  "prompt_hint": "Preserve facial proportions, blonde styling, and full-face beauty framing.",
  "provider_use": "reference_input"
}
```

`use_asset` controls whether the asset is active. `asset_type` tells the pipeline whether the file is an image or video. `role`, `label`, and `prompt_hint` become semantic instructions in the Kling prompt.

For the deep guide, read [docs/tutorial.md](/app/docs/tutorial.md). For the practical runbook, read [docs/walkthrough.md](/app/docs/walkthrough.md). For script fields, read [docs/script_tutorial.md](/app/docs/script_tutorial.md).
