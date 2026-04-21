# Pipeline Tutorial

This is the technical guide. It explains how the pipeline works, where data flows, and how to extend the video-generation model layer.

For a command-only guide, read [walkthrough.md](./walkthrough.md).

## Mental Model

The pipeline is:

```text
Input project -> train artifacts -> script references -> shot plan -> provider API -> generated clips -> render
```

`train` does not fine-tune Sora, Veo, or Kling. It analyzes your reference videos and builds local artifacts:

1. `video_analyses.json`
2. `style_profile.json`
3. `asset_inventory.json`
4. `resolved_run_config.json`

`generate` uses those artifacts plus the script to call a selected video-generation provider for each shot.

## Project Layout

The new project layout is rooted at `/app/Input`:

```text
/app/Input/
  Blonde Blazer Romance/
    Scripts/
      sample1.json
    Supporting Data/
      general_assets/
        video/
        images/
      closeups/
      broll/
      portraits/
      product_shots/
      style_references/
      brand_assets/
      audio/
      docs/
```

The optional future video source is configured by:

```yaml
asset_subfolders:
  reference_videos: Supporting Data/general_assets/video
```

The current active path is image-to-video, so scene images are enough. Videos are optional support data for analysis today and future video-input generation later.

## Configuration Layers

`.env` contains machine-specific paths and secrets:

```bash
VIDEO_INPUT_DIR=/app/Input
VIDEO_OUTPUT_DIR="/app/Video Output"
PIPELINE_ARTIFACTS_DIR=/app/artifacts

OPENAI_API_KEY=
GOOGLE_VERTEX_PROJECT=
GOOGLE_VERTEX_LOCATION=us-central1
KLING_API_ACCESS_KEY=
KLING_API_SECRET_KEY=
```

`run_parameters.yaml` contains the creative run:

```yaml
input_folder: Blonde Blazer Romance
script_file: Scripts/sample1.json

selection:
  use_input_images: true
  use_input_videos: false

generation:
  backend: auto

models:
  video_generation_model: kling_2_6_std
```

The current default is intentionally cost-conscious: Kling multi-image-to-video, silent, 5 seconds, `540p`, and up to four scene reference images.

`selection.use_input_images` and `selection.use_input_videos` decide what `train` consumes. For the current Kling path, images are on and videos are off. You can override this from the CLI:

```bash
python -m pipeline train --run-config /app/run_parameters.yaml --use-input-images --no-use-input-videos
python -m pipeline train --run-config /app/run_parameters.yaml --use-input-images --use-input-videos
```

Relative script paths are resolved in this order:

1. `/app/Input/<input_folder>/<script_file>`
2. `/app/Input/<input_folder>/Scripts/<script_file>`
3. `SCRIPTS_DIR/<script_file>`

That means both of these work:

```yaml
script_file: Scripts/sample1.json
script_file: sample1.json
```

## Model Selection

The model abstraction lives in [pipeline/video_models.py](../pipeline/video_models.py).

The key dataclass is:

```python
@dataclass(frozen=True)
class VideoModelPreset:
    preset_id: str
    provider: str
    model: str
    label: str
    price_tier: str
    quality_tier: str
```

`models.video_generation_model` can be either a friendly preset or a raw provider model id.

Preset examples:

```yaml
models:
  video_generation_model: kling_2_6_std
```

```yaml
models:
  video_generation_model: veo_3_1_fast
```

```yaml
models:
  video_generation_model: sora_2_pro
```

When `generation.backend: auto`, the preset decides the provider:

1. `sora_2` and `sora_2_pro` use `openai_video`.
2. `veo_3_1_lite`, `veo_3_1_fast`, and `veo_3_1_quality` use `google_veo`.
3. `kling_2_5_turbo`, `kling_2_6_std`, and `kling_2_6_pro` use `kling`.

For cheap Kling testing, the most important YAML is:

```yaml
generation:
  backend: auto
  kling_generation_mode: multi_image_to_video
  kling_local_image_transport: base64
  video_resolution: 540p
  video_duration_seconds: 5
  kling_sound: false

models:
  video_generation_model: kling_2_6_std
```

To increase quality later, first try:

```yaml
models:
  video_generation_model: kling_2_6_pro
```

Then consider increasing:

```yaml
generation:
  video_resolution: 720p
  video_duration_seconds: 10
```

You can inspect presets from the CLI:

```bash
python -m pipeline video-models
```

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
    size: str | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    references: list[PreparedReference] = field(default_factory=list)
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

The dispatcher is:

```python
def get_video_provider(provider_name: str) -> VideoProvider:
    if provider_name == "openai_video":
        return OpenAIVideoProvider()
    if provider_name == "google_veo":
        return GoogleVeoProvider()
    if provider_name == "kling":
        return KlingVideoProvider()
    raise ValueError(...)
```

This keeps provider-specific auth, request payloads, polling, and download logic out of the planner.

## Provider Behavior

OpenAI/Sora:

1. Requires `OPENAI_API_KEY`.
2. Calls the OpenAI video API.
3. Sends `model`, `prompt`, `seconds`, and `size`.
4. Uses one local image reference when available.
5. If the selected reference is a video, the pipeline extracts a frame first.

Google Veo:

1. Requires `GOOGLE_VERTEX_PROJECT`.
2. Uses Vertex AI long-running prediction endpoints.
3. Sends `durationSeconds`, `aspectRatio`, `resolution`, and optional asset reference images.
4. Polls `fetchPredictOperation`.
5. Writes returned base64 video bytes or downloads a returned `gs://` object with `gcloud storage cp`.

Kling:

1. Requires `KLING_API_ACCESS_KEY` and `KLING_API_SECRET_KEY`.
2. Uses `KLING_BASE_URL`, defaulting to `https://api.klingapi.com`.
3. Uses multi-image-to-video by default.
4. Sends 2-4 scene images in `image_list`.
5. Sends local images as base64 by default, so you do not need public hosting for early tests.
6. Keeps `sound: false`, `duration: "5"`, and `resolution: "540p"` in the default run config.
7. Polls the returned task id and downloads the result URL.

## Kling Multi-Image To Video

The Kling implementation is designed around the common multi-image flow documented by Kling gateways:

```http
POST /v1/videos/multi-image2video
GET  /v1/videos/multi-image2video/{task_id}
```

The request body looks like:

```json
{
  "model_name": "kling-v2.6",
  "prompt": "Scene prompt...",
  "duration": "5",
  "aspect_ratio": "9:16",
  "resolution": "540p",
  "mode": "standard",
  "sound": false,
  "image_list": [
    { "image": "<base64 image 1 or public URL>" },
    { "image": "<base64 image 2 or public URL>" }
  ]
}
```

The important implementation pieces are:

1. `pipeline/video_models.py` maps `kling_2_6_std` to provider `kling` and model `kling-v2.6`.
2. `pipeline/video_providers.py` builds the Kling payload.
3. `generation.kling_generation_mode: multi_image_to_video` selects the multi-image endpoint.
4. `generation.kling_local_image_transport: base64` allows local scene images to be sent without public URLs.
5. `generation.kling_model_field: model_name` matches multi-image gateways that expect `model_name` instead of `model`.
6. `generation.kling_multi_image_min_images` and `generation.kling_multi_image_max_images` control the 2-4 image window.

If your Kling gateway uses a different endpoint, you do not need to edit code. Change `.env`:

```bash
KLING_BASE_URL=https://your-kling-gateway.example.com
KLING_MULTI_IMAGE_ENDPOINT=/v1/videos/multi-image2video
KLING_STATUS_ENDPOINT_TEMPLATE={endpoint}/{task_id}
```

If your gateway rejects base64 and only accepts public URLs:

```yaml
generation:
  kling_local_image_transport: url
  public_asset_base_url: https://your-public-file-host.example.com/Blonde%20Blazer%20Romance
```

With `url` transport, local paths are converted to public URLs only when `public_asset_base_url` is set. Otherwise they remain prompt-only and the provider will not receive the pixels.

## Script Reference Assets

The script parser lives in [pipeline/script_io.py](../pipeline/script_io.py).

A scene can contain:

```json
"reference_assets": [
  {
    "path": "Supporting Data/general_assets/images/Scene 1/1.png",
    "role": "character",
    "label": "lead talent face reference",
    "prompt_hint": "Preserve facial proportions and beauty-ad framing.",
    "provider_use": "reference_input"
  }
]
```

Supported reference fields:

1. `reference_assets`
2. `supporting_assets`
3. `supporting_data`
4. `reference_images`
5. `general_assets_images`
6. `general_assets_video`
7. legacy single `reference_image`

Path resolution tries:

1. absolute path
2. script folder
3. project root
4. `Supporting Data`
5. a field-specific helper folder, such as `Supporting Data/general_assets/images`

If a reference points to a directory, the parser expands supported image/video files inside it.

## Do Models Understand The Files?

Not automatically in the way a human would.

If you upload or attach a picture without explanation, the provider sees pixels but may not know whether those pixels mean character identity, wardrobe, composition, lighting, brand, or style.

That is why the script uses semantic fields:

```json
{
  "role": "wardrobe",
  "label": "blonde blazer wardrobe reference",
  "prompt_hint": "Use this for blazer color, fit, neckline, and luxury fashion styling."
}
```

The pipeline uses supporting data in two channels:

1. Text channel: `role`, `label`, and `prompt_hint` are inserted into the generation prompt.
2. Media channel: the actual image/video-derived frame is attached only when the provider supports it.

This means every supporting asset should answer two questions:

1. What is this file?
2. How should the model use it?

## Shot Planning

The planner lives in [pipeline/planning.py](../pipeline/planning.py).

For each scene it:

1. resolves timing
2. selects a matching inventory asset
3. carries scene `reference_assets` into the shot plan
4. builds continuity notes
5. builds a provider prompt
6. records the selected source asset and media kind

The prompt includes:

1. continuity profile
2. scene action
3. motion strategy
4. selected asset guidance
5. reference asset roles and hints
6. pacing and voice style
7. scene metadata
8. target downstream model

## Generation

The generation stage lives in [pipeline/generation.py](../pipeline/generation.py).

The important flow is:

```python
model_selection = resolve_video_model_selection(run_parameters)
provider = get_video_provider(model_selection.provider)

for item in plan.items:
    request = VideoGenerationRequest(...)
    result = provider.generate(request)
```

Before calling the provider, the stage prepares references:

1. HTTP references remain URLs.
2. Local images remain files.
3. Local videos are converted into frame images for providers that need image references.
4. Sora/OpenAI image references are resized to the requested output size.
5. Kling local images are sent as base64 by default, or as public URLs when `kling_local_image_transport: url` and `generation.public_asset_base_url` are set.

Duration is snapped to provider-supported buckets:

1. OpenAI: `4`, `8`, `12`, `16`, `20`
2. Google Veo: `4`, `6`, `8`
3. Kling: `5`, `10`

## Rendering

The renderer lives in [pipeline/render.py](../pipeline/render.py).

It expects generated video assets. If a shot has no generated `.mp4`, it raises an error instead of pretending a still pan is equivalent to generative video.

The renderer:

1. opens each generated clip
2. samples frames at the target FPS
3. applies light grading and overlays
4. muxes optional voiceover audio
5. writes the final draft `.mp4`

## Adding Another Provider

To add a provider:

1. Add a preset in [pipeline/video_models.py](../pipeline/video_models.py).
2. Add a provider class in [pipeline/video_providers.py](../pipeline/video_providers.py).
3. Register it in `get_video_provider`.
4. Add any new secrets to [pipeline/config.py](../pipeline/config.py) and `.env.example`.
5. Document provider reference behavior in this file and [walkthrough.md](./walkthrough.md).

Provider class skeleton:

```python
class MyVideoProvider(VideoProvider):
    provider_name = "my_provider"

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        # 1. validate auth
        # 2. submit async job
        # 3. poll until complete
        # 4. download mp4 to request.output_path
        return VideoGenerationResult(asset_path=request.output_path, remote_id="job-id")
```

## Good Iteration Strategy

Use cheap models while prompts and scene references are still changing:

1. Start with `kling_2_6_std` or `veo_3_1_lite`.
2. Keep scene durations short.
3. Inspect `shot_plan.json` before spending on expensive generations.
4. Move promising shots to `veo_3_1_fast`, `kling_2_6_pro`, or `sora_2`.
5. Use `sora_2_pro` or `veo_3_1_quality` only for final passes.

## Useful Commands

```bash
python -m pipeline video-models
python -m pipeline show-run-config --run-config /app/run_parameters.yaml
python -m pipeline train --run-config /app/run_parameters.yaml
python -m pipeline generate --run-config /app/run_parameters.yaml
python -m json.tool /app/artifacts/sample1/shot_plan.json | sed -n '1,260p'
python -m json.tool /app/artifacts/sample1/generated_assets.json | sed -n '1,220p'
```
