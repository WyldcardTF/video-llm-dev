# Pipeline Walkthrough

This is the practical command-line guide. For code-level internals, read [tutorial.md](./tutorial.md).

## What You Need

1. A project folder under `/app/Input`.
2. A script inside that project, usually `Scripts/sample1.json`.
3. At least two scene images referenced from the script for Kling multi-image generation.
4. A provider key for whichever video model you select.

The sample project is:

```bash
/app/Input/Blonde Blazer Romance
```

## 1. Inspect The Project

```bash
find "/app/Input/Blonde Blazer Romance" -maxdepth 4 -type d | sort
find "/app/Input/Blonde Blazer Romance" -maxdepth 5 -type f | sort
python -m json.tool "/app/Input/Blonde Blazer Romance/Scripts/sample1.json"
```

The important folders are:

1. `Scripts/` for JSON scripts.
2. `Supporting Data/general_assets/video/` for optional future video references.
3. `Supporting Data/general_assets/images/` for scene images.
4. `Supporting Data/closeups`, `broll`, `portraits`, `product_shots`, `style_references`, `brand_assets`, `audio`, and `docs` for optional support.

## 2. Choose A Video Model

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

1. `kling_2_5_turbo` for the cheapest scratchpad if available.
2. `kling_2_6_std` for low-cost Kling multi-image testing: silent, 5 seconds, 540p.
3. `veo_3_1_lite` for low-cost Veo prompt tests.
4. `veo_3_1_fast` or `kling_2_6_pro` for stronger promising shots.
5. `sora_2`, `veo_3_1_quality`, or `sora_2_pro` for higher-quality passes.

## 3. Set Provider Secrets

Use only the provider you plan to run.

OpenAI/Sora:

```bash
OPENAI_API_KEY=...
```

Google Veo on Vertex AI:

```bash
GOOGLE_VERTEX_PROJECT=your-google-cloud-project
GOOGLE_VERTEX_LOCATION=us-central1
```

If you do not set `GOOGLE_VERTEX_ACCESS_TOKEN`, the pipeline tries Application Default Credentials and then `gcloud auth print-access-token`.

Kling:

```bash
KLING_API_ACCESS_KEY=...
KLING_API_SECRET_KEY=...
KLING_BASE_URL=https://api.klingapi.com
```

For the default Kling setup, that is enough. The pipeline sends 2-4 local scene images as base64 through the multi-image-to-video endpoint.

## 4. Inspect The Run Config

```bash
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
```

Check:

1. `input_folder` is `Blonde Blazer Romance`.
2. `script_file` resolves to `Input/Blonde Blazer Romance/Scripts/sample1.json`.
3. `asset_subfolders.reference_videos` points to `Supporting Data/general_assets/video`.
4. `models.video_generation_model` is the preset you want.
5. `generation.video_aspect_ratio` is quoted as `"9:16"` in YAML.

## 5. Edit Scene References

Each scene can include `reference_assets`:

```json
{
  "path": "Supporting Data/general_assets/images/Scene 1/1.png",
  "role": "character",
  "label": "lead talent face reference",
  "prompt_hint": "Preserve the lead talent's facial proportions and premium beauty-ad framing.",
  "provider_use": "reference_input"
}
```

What the fields mean:

1. `path` points to a local file/folder under the project or to an HTTP URL.
2. `role` tells the prompt what the asset means, such as `character`, `wardrobe`, `composition`, `style`, or `motion_reference`.
3. `label` is a human-readable name.
4. `prompt_hint` is the most important semantic instruction.
5. `provider_use` tells future code and humans whether the asset is intended as `reference_input`, `prompt_only`, `prompt_and_reference`, or `prompt_and_frame`.

## 6. Train

```bash
python -m pipeline train --run-config /app/run_parameters.yaml
```

This command:

1. inventories images/videos under `Supporting Data`
2. optionally scans supporting videos if present
3. samples frame, motion, brightness, palette, and audio characteristics only for videos that exist
4. builds an image-first style profile when no videos exist
5. writes reusable artifacts under `/app/artifacts/sample1`

Input-mode flags:

```bash
python -m pipeline train --run-config /app/run_parameters.yaml --use-input-images --no-use-input-videos
python -m pipeline train --run-config /app/run_parameters.yaml --use-input-images --use-input-videos
```

Use the first command for the current Kling image-to-video flow. Use the second later when you want videos analyzed as additional style/motion support.

Inspect:

```bash
python -m json.tool /app/artifacts/sample1/resolved_run_config.json | sed -n '1,240p'
python -m json.tool /app/artifacts/sample1/style_profile.json | sed -n '1,220p'
python -m json.tool /app/artifacts/sample1/asset_inventory.json | sed -n '1,260p'
```

## 7. Generate

```bash
python -m pipeline generate --run-config /app/run_parameters.yaml
```

This command:

1. loads trained artifacts
2. loads the scene script
3. builds continuity and shot-plan JSON
4. prepares provider references
5. calls the selected video-generation provider once per shot
6. assembles generated clips into `/app/Video Output/sample1_draft.mp4`

Inspect:

```bash
python -m json.tool /app/artifacts/sample1/shot_plan.json | sed -n '1,280p'
python -m json.tool /app/artifacts/sample1/generated_assets.json | sed -n '1,220p'
ls -lh "/app/Video Output"
```

## How Supporting Data Is Used

The pipeline is explicit rather than magical:

1. Videos in `Supporting Data/general_assets/video` are optional for now. They are reserved for future video-input generation and can still be analyzed if present.
2. Other videos under `Supporting Data` are optional; they are scanned and inventoried for style and shot planning.
3. Images are inventoried and can be attached to scenes through `reference_assets`.
4. The model receives semantic text from `role`, `label`, and `prompt_hint`.
5. The model receives actual image files only when the provider supports that input.
6. Kling multi-image uses local base64 images by default. If your gateway rejects base64, switch to URL transport with `generation.public_asset_base_url`.
7. 3D models, docs, overlays, brand assets, music, and SFX are inventoried or preserved as structure today, but they are not yet directly rendered into generated video.

## Provider Reference Behavior

OpenAI/Sora:

1. Uses text prompts.
2. Can use one prepared local image reference as the opening frame.
3. If the selected reference is a video, the pipeline extracts a still frame first.

Google Veo:

1. Uses text prompts through Vertex AI.
2. Veo 3.1 Fast/Quality can receive local asset reference images.
3. Veo 3.1 Lite is treated as prompt-first/low-cost.
4. Style reference images are kept as prompt guidance because Veo 3.1 does not support style-reference images the same way older Veo style flows did.

Kling:

1. Uses text prompts.
2. Uses multi-image-to-video by default when at least two scene images are available.
3. Sends local image files as base64 by default.
4. Can switch to public URL transport if your Kling gateway requires URLs.

## Common Changes

Change model:

```yaml
models:
  video_generation_model: veo_3_1_fast
```

Use Sora:

```yaml
models:
  video_generation_model: sora_2
```

Use higher quality Sora:

```yaml
models:
  video_generation_model: sora_2_pro
```

Use Google Veo quality:

```yaml
models:
  video_generation_model: veo_3_1_quality
```

Use Kling Pro:

```yaml
models:
  video_generation_model: kling_2_6_pro
```

Run both stages:

```bash
python -m pipeline run --run-config /app/run_parameters.yaml
```

## Troubleshooting

Not enough Kling images:

Add at least two scene image references in `Scripts/sample1.json`, or lower `generation.kling_multi_image_min_images` only if your provider supports one-image mode.

Wrong script path:

Use `script_file: Scripts/sample1.json` or an absolute path.

Kling ignores local images:

Check `generation.kling_local_image_transport`. The default is `base64`, which uploads local image bytes in `image_list`. If your gateway only accepts URLs, set `kling_local_image_transport: url` and provide `generation.public_asset_base_url`.

Google Veo auth fails:

Set `GOOGLE_VERTEX_PROJECT`, authenticate with `gcloud auth application-default login`, or set `GOOGLE_VERTEX_ACCESS_TOKEN`.

The generated clip is expensive:

Drop to `kling_2_6_std`, `kling_2_5_turbo`, or `veo_3_1_lite`, reduce scene count, and keep durations short.
