# Pipeline Walkthrough

This is the practical command-line guide for the Kling-only pipeline. For code-level internals, read [tutorial.md](./tutorial.md).

## What You Need

1. A project folder under `/app/Input`.
2. A script inside that project, usually `Scripts/script1.json`.
3. Active `asset_type: image` references for Kling generation.
4. Kling API keys.

## 1. Inspect The Project

```bash
find "/app/Input/Blonde Blazer Romance" -maxdepth 4 -type d | sort
find "/app/Input/Blonde Blazer Romance" -maxdepth 5 -type f | sort
python -m json.tool "/app/Input/Blonde Blazer Romance/Scripts/script1.json"
```

Scene folders such as `Supporting Data/.../scene 1` are matched to script scene names case-insensitively. Folders named `general` are treated as global context.

## 2. Choose A Kling Model

List presets:

```bash
python -m pipeline video-models
```

Set the preset in [run_parameters.yaml](../run_parameters.yaml):

```yaml
generation:
  backend: auto

models:
  video_generation_model: kling_2_6_std
```

Good iteration ladder:

1. `kling_2_5_turbo` for cheap scratch work if your account exposes it.
2. `kling_2_6_std` for default 5-second 540p tests.
3. `kling_2_6_pro` for stronger promising shots.
4. `kling_2_6_pro_audio` when generated audio is needed.

## 3. Set Kling Secrets

```bash
KLING_API_ACCESS_KEY=...
KLING_API_SECRET_KEY=...
KLING_BASE_URL=https://api-singapore.klingai.com
```

The default flow uses `POST /v1/videos/multi-image2video` and sends local scene images as base64, so public image hosting is not required.

## 4. Inspect The Run Config

```bash
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
```

Check:

1. `input_folder` is `Blonde Blazer Romance`.
2. `script_file` resolves to the script JSON.
3. `models.video_generation_model` is a Kling preset.
4. `generation.video_aspect_ratio` is `"9:16"`.
5. `generation.kling_fit_reference_images` is `true` to fit landscape references into portrait-safe frames.
6. `render.output_width` and `render.output_height` are blank unless you want to override the standard `1080x1920` vertical render.

## 5. Edit Scene References

Each scene can include `reference_assets`:

```json
{
  "path": "Supporting Data/general_assets/images/scene 1/1.png",
  "use_asset": true,
  "asset_type": "image",
  "role": "character",
  "label": "lead talent face reference",
  "prompt_hint": "Preserve the lead talent's facial proportions and full-face beauty framing.",
  "provider_use": "reference_input"
}
```

Important fields:

1. `path` points to a local file/folder under the project or to an HTTP URL.
2. `use_asset` enables or disables the asset.
3. `asset_type` is `image` or `video`.
4. `role`, `label`, and `prompt_hint` explain how Kling should use the asset.
5. `provider_use` documents intent, such as `reference_input`, `prompt_only`, or `prompt_and_reference`.

For full-face portrait shots, keep the scene text direct: say `full face visible`, `hairline and chin inside frame`, and `no half-face crop`.

## 6. Train

```bash
python -m pipeline train --run-config /app/run_parameters.yaml
```

Training inventories images, analyzes active video references if any are enabled, builds a style profile, and writes artifacts under `/app/artifacts/script1`.

## 7. Generate

```bash
python -m pipeline generate --run-config /app/run_parameters.yaml
```

Generation loads the artifacts, builds a shot plan, prepares Kling references, calls Kling once per shot, and renders the next progressive draft in `/app/Video Output`.

For `9:16`, the renderer uses a standard `1080x1920` delivery canvas by default. Generated clips are fitted into that canvas instead of cover-cropped, so a portrait Kling clip is not accidentally cropped by landscape input-image dimensions.

With `output_file: script1_draft.mp4`, outputs are:

1. `script1_draft_1.mp4`
2. `script1_draft_2.mp4`
3. `script1_draft_3.mp4`

Inspect:

```bash
python -m json.tool /app/artifacts/script1/shot_plan.json | sed -n '1,280p'
python -m json.tool /app/artifacts/script1/generated_assets.json | sed -n '1,220p'
ls -lh "/app/Video Output"
```

## Re-Render Without Calling Kling

If the generated Kling clip is good but the final format, crop, overlay, or render size needs adjustment, re-render existing generated assets locally:

```bash
python -m pipeline render --run-config /app/run_parameters.yaml
```

This uses `/app/artifacts/script1/shot_plan.json` and the existing generated clips. It does not call Kling or spend credits.

## Kling Reference Behavior

1. `multi_image_to_video` sends 2-4 active image references in `image_list`.
2. `image_to_video` sends one image as `image`.
3. `text_to_video` sends only the prompt.
4. Local images are base64 by default.
5. Local base64 images are fit into the target aspect ratio before upload, reducing accidental portrait crops from landscape inputs.
6. `kling_extra_payload` can carry gateway-specific fields.
