# Blonde Blazer Romance Input Bundle

This folder is the selected `input_folder` for `run_parameters.yaml`.

The current layout is:

1. `Scripts/`
   Structured JSON scripts for this project. The sample run uses `Scripts/sample1.json`.
2. `Supporting Data/general_assets/video/`
   Required primary reference video pool. At least one supported video must exist here while `selection.require_videos: true`.
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

Only the primary reference video pool is mandatory. Everything else is supporting material.

Scene scripts can explain what each supporting file means:

```json
{
  "path": "Supporting Data/general_assets/images/Scene 1/1.png",
  "role": "character",
  "label": "lead talent face reference",
  "prompt_hint": "Preserve the lead talent's facial proportions and premium beauty-ad framing.",
  "provider_use": "reference_input"
}
```

The pipeline does not treat every file equally. The `role`, `label`, and `prompt_hint` fields are inserted into the generation prompt so the model knows whether an image is meant to guide identity, wardrobe, composition, style, or motion.
