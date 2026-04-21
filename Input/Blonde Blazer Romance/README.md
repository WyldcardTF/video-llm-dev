# Blonde Blazer Romance Input Bundle

This folder is the selected `input_folder` for `run_parameters.yaml`.

The current layout is:

1. `Scripts/`
   Structured JSON scripts for this project. The sample run uses `Scripts/script1.json`.
2. `Supporting Data/general_assets/video/`
   Optional future video-reference pool. The current Kling multi-image flow does not require videos.
3. `Supporting Data/general_assets/images/`
   Scene-specific image references. For example, `Scene 1/1.png` can be referenced from the script.
4. `Supporting Data/closeups/videos/` and `Supporting Data/closeups/images/`
   Optional close-up reference clips and images.
5. `Supporting Data/broll/videos/` and `Supporting Data/broll/images/`
   Optional inserts, secondary action, product details, and atmosphere.
6. `Supporting Data/portraits/` and `Supporting Data/product_shots/`
   Optional identity, wardrobe, and garment references.
7. `Supporting Data/style_references/`
   Optional moodboards and visual inspiration.
8. `Supporting Data/brand_assets/`, `Supporting Data/overlays/`, and `Supporting Data/docs/`
   Optional brand, design, storyboard, transcript, and planning material.
9. `Supporting Data/audio/`
   Optional voiceover, music, and sound-effect folders.

No video folder is mandatory for the current Kling multi-image flow. Active inputs are controlled by `use_asset` and `asset_type` in `Scripts/script1.json`.

Folder naming convention:

1. `general` folders provide context for the whole video.
2. Scene folders such as `scene 1` provide context only for the matching script scene.
3. Matching is case-insensitive.

Scene scripts can explain what each supporting file means:

```json
{
  "path": "Supporting Data/general_assets/images/Scene 1/1.png",
  "use_asset": true,
  "asset_type": "image",
  "role": "character",
  "label": "lead talent face reference",
  "prompt_hint": "Preserve the lead talent's facial proportions and premium beauty-ad framing.",
  "provider_use": "reference_input"
}
```

The pipeline does not treat every file equally. `use_asset: false` disables a listed file, `asset_type: image` or `video` tells the code how to treat it, and `role`, `label`, and `prompt_hint` tell the model whether an asset is meant to guide identity, wardrobe, composition, style, or motion.
