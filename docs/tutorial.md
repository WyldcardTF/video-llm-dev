# Pipeline Tutorial

This is the technical guide for the Kling-only video pipeline. For command usage, read [walkthrough.md](./walkthrough.md).

## Mental Model

```text
Input project -> train artifacts -> script references -> shot plan -> Kling API -> generated clips -> render
```

`train` does not fine-tune Kling. It inventories images, analyzes active script video references when present, and builds local artifacts:

1. `video_analyses.json`
2. `style_profile.json`
3. `asset_inventory.json`
4. `resolved_run_config.json`

`generate` uses those artifacts plus the script to call Kling for each shot.

## Model Selection

The model abstraction lives in [pipeline/video_models.py](../pipeline/video_models.py). It contains only Kling presets:

1. `kling_2_5_turbo`
2. `kling_2_6_std`
3. `kling_2_6_pro`
4. `kling_2_6_pro_audio`

When `generation.backend: auto`, the selected preset resolves to the Kling provider.

## Provider Layer

The provider API layer lives in [pipeline/video_providers.py](../pipeline/video_providers.py).

It defines one request shape:

```python
@dataclass(frozen=True)
class VideoGenerationRequest:
    prompt: str
    negative_prompt: str
    output_path: Path
    model_selection: VideoModelSelection
    run_parameters: RunParameters
    settings: Settings
    duration_seconds: int
    aspect_ratio: str | None = None
    resolution: str | None = None
    references: list[PreparedReference] = field(default_factory=list)
    provider_options: dict[str, Any] = field(default_factory=dict)
```

And one result shape:

```python
@dataclass(frozen=True)
class VideoGenerationResult:
    asset_path: Path
    remote_id: str | None = None
    revised_prompt: str | None = None
    used_reference_paths: list[str] = field(default_factory=list)
```

`get_video_provider` returns only `KlingVideoProvider`.

## Kling Payloads

Kling requires `KLING_API_ACCESS_KEY` and `KLING_API_SECRET_KEY`.

Default multi-image request:

```http
POST /v1/videos/multi-image2video
GET  /v1/videos/multi-image2video/{task_id}
```

Representative body:

```json
{
  "model_name": "kling-v1-6",
  "prompt": "Scene prompt...",
  "negative_prompt": "Avoid warped faces...",
  "duration": "5",
  "aspect_ratio": "9:16",
  "resolution": "540p",
  "mode": "std",
  "sound": "off",
  "cfg_scale": 0.65,
  "image_list": [
    { "image": "<base64 image 1 or public URL>" },
    { "image": "<base64 image 2 or public URL>" }
  ]
}
```

Kling image-to-video fallback:

```http
POST /v1/videos/image2video
```

Representative body:

```json
{
  "model_name": "kling-v2-6",
  "prompt": "Scene prompt...",
  "image": "<base64 image or public URL>"
}
```

Kling text-to-video fallback:

```http
POST /v1/videos/text2video
```

## Kling Options

Common fields are mapped directly:

1. `prompt` comes from the scene, continuity profile, and reference hints.
2. `negative_prompt` comes from the continuity profile.
3. `model_name` or `model` is controlled by `generation.kling_model_field`.
4. `duration` is snapped to `5` or `10`.
5. `aspect_ratio` comes from `generation.video_aspect_ratio`.
6. `resolution` comes from `generation.video_resolution`.
7. `mode` comes from `generation.kling_mode` or the selected preset.
8. `sound` comes from `generation.kling_sound` or the selected preset.
9. `cfg_scale` comes from `generation.kling_cfg_scale` or scene `provider_options.kling.cfg_scale`.
10. `callback_url` and `external_task_id` come from `generation.kling_callback_url` and `generation.kling_external_task_id`.
11. `camera_control` comes from `generation.kling_camera_control` or scene `provider_options.kling.camera_control`.
12. `kling_extra_payload` is merged into the request for gateway-specific fields.

Scene-level Kling overrides live in the script:

```json
"provider_options": {
  "kling": {
    "cfg_scale": 0.65
  }
}
```

## Reference Preparation

Before calling Kling, [pipeline/generation.py](../pipeline/generation.py):

1. collects active scene references
2. resolves local paths and HTTP URLs
3. fits local base64 image references into the target aspect ratio when `kling_fit_reference_images: true`
4. builds a prompt from scene text, continuity, and reference hints
5. sends references to Kling according to `generation.kling_generation_mode`

The portrait-fit step is important for landscape source images used in a `9:16` output. It keeps the full source visible on a portrait canvas instead of letting the model infer a tight crop from a landscape image.

## Rendering

The renderer lives in [pipeline/render.py](../pipeline/render.py). It expects generated video assets, samples frames at the target FPS, applies light grading and overlays, and writes the final draft.

Final output naming is progressive. With `output_file: script1_draft.mp4`, the CLI writes `script1_draft_1.mp4`, then `script1_draft_2.mp4`, and continues upward.

## Useful Commands

```bash
python -m pipeline video-models
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
python -m pipeline train --run-config /app/run_parameters.yaml
python -m pipeline generate --run-config /app/run_parameters.yaml
python -m json.tool /app/artifacts/script1/shot_plan.json | sed -n '1,260p'
python -m json.tool /app/artifacts/script1/generated_assets.json | sed -n '1,220p'
```
