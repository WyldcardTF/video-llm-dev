# Script Tutorial

This file explains the structured JSON script used by the Kling-only pipeline.

## Top-Level Fields

`project` describes the creative brief. The planner uses fields such as `name`, `objective`, `target_audience`, `aspect_ratio`, and `voice_style_goal` as style and continuity guidance.

`global_style` describes the shared look of the whole video. Useful fields are `mood`, `color_palette`, `editing_rhythm`, `camera_language`, `music_direction`, and `reference_policy`.

`global_style.general_reference_assets` is a list of references attached to every scene. These are good for global motion, lighting, brand, or style references. Set `use_asset: false` to keep a reference documented but inactive.

`scenes` is the ordered list of shots to generate. Each item becomes one Kling-generated shot.

## Scene Fields

`name` is the scene title. It is also used for matching folders such as `Supporting Data/.../scene 1`.

`description` is the main action prompt. Keep it literal and visual. For portrait Kling outputs, specify the crop directly: full face visible, centered eye contact, hairline and chin inside frame, no half-face crop.

`time start`, `time end`, and `duration` describe timing. The planner honors `duration` when `planning.honor_script_timing` is true.

`camera`, `shot_type`, `mood`, `subject`, `wardrobe`, `preferred_asset_types`, and `notes` are scene metadata. They are inserted into the generation prompt when `planning.include_scene_metadata_in_prompt` is true.

`text overlay` becomes the rendered caption overlay.

`transition` controls the render transition into the next shot. Current renderer support is `cut`, `crossfade`, `fade`, and `dissolve`.

`provider_options` stores scene-level provider overrides. Kling options can be placed under `provider_options.kling`.

```json
"provider_options": {
  "kling": {
    "cfg_scale": 0.65
  }
}
```

## Reference Asset Fields

Each scene can include `reference_assets`:

```json
{
  "path": "Supporting Data/general_assets/images/scene 1/1.png",
  "role": "character",
  "label": "lead talent face reference",
  "prompt_hint": "Preserve full-face framing and identity.",
  "provider_use": "reference_input",
  "use_asset": true,
  "asset_type": "image"
}
```

`path` points to a local file, local folder, or HTTP URL. Relative paths resolve from the script folder, project root, and `Supporting Data`.

`use_asset` enables or disables the reference without deleting it from the script.

`asset_type` should be `image` or `video`. It tells the pipeline how to prepare the file.

`role` explains what the asset means, such as `character`, `wardrobe`, `composition`, `style`, or `motion_reference`.

`label` is a readable name that appears in prompts and manifests.

`prompt_hint` is the most important semantic instruction. Use it to say exactly how Kling should use the file.

`provider_use` documents intent. Common values are `reference_input`, `prompt_only`, `prompt_and_reference`, and `prompt_and_frame`.

## Kling Behavior

If `generation.kling_generation_mode` is `multi_image_to_video`, Kling receives 2-4 active scene images through `image_list`.

If the mode is `image_to_video`, Kling receives the first active image as `image`.

If the mode is `text_to_video`, Kling receives only the text prompt.

Local Kling base64 image references are fitted into the target aspect ratio before upload. This matters when the source image is landscape but the output is `9:16`; fitting keeps the full face visible instead of letting a portrait crop remove half the face.

Final renders are progressive. With `output_file: script1_draft.mp4`, the CLI writes `script1_draft_1.mp4`, `script1_draft_2.mp4`, and so on.
