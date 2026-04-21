from __future__ import annotations

from collections import Counter
from pathlib import Path

import cv2

from .io_utils import read_json
from .models import AssetInventory, StyleProfile, VideoAnalysis


def build_style_profile(
    analyses: list[VideoAnalysis],
    asset_inventory: AssetInventory | None = None,
) -> StyleProfile:
    if not analyses:
        return _build_image_first_style_profile(asset_inventory)

    return _build_video_style_profile(analyses)


def _build_video_style_profile(analyses: list[VideoAnalysis]) -> StyleProfile:
    if not analyses:
        raise ValueError("At least one video analysis is required for video-based style profiling.")

    resolution_counts = Counter((item.width, item.height) for item in analyses)
    target_width, target_height = resolution_counts.most_common(1)[0][0]

    preferred_shot_duration_s = sum(item.estimated_shot_length_s for item in analyses) / len(analyses)
    average_brightness = sum(item.average_brightness for item in analyses) / len(analyses)
    average_motion = sum(item.motion_score for item in analyses) / len(analyses)

    color_counter = Counter(color for item in analyses for color in item.color_palette)
    reference_images = [
        sample.image_path
        for item in analyses
        for sample in item.sample_frames
    ]

    if preferred_shot_duration_s <= 2.5:
        pacing_label = "fast"
    elif preferred_shot_duration_s <= 4.5:
        pacing_label = "medium"
    else:
        pacing_label = "slow"

    voice_descriptions = [
        item.audio.voice_style
        for item in analyses
        if item.audio.voice_style
    ]
    voice_style = ", ".join(dict.fromkeys(voice_descriptions)) if voice_descriptions else "voice analysis not available"

    style_summary = (
        f"{pacing_label.capitalize()} pacing with {average_motion:.2f} motion intensity, "
        f"{average_brightness:.2f} brightness, palette led by "
        f"{', '.join(color for color, _ in color_counter.most_common(3))}, "
        f"and a {voice_style}."
    )

    return StyleProfile(
        source_videos=[item.source_path for item in analyses],
        target_width=target_width,
        target_height=target_height,
        pacing_label=pacing_label,
        preferred_shot_duration_s=round(preferred_shot_duration_s, 2),
        average_brightness=round(average_brightness, 3),
        average_motion=round(average_motion, 3),
        color_palette=[color for color, _ in color_counter.most_common(5)],
        voice_style=voice_style,
        style_summary=style_summary,
        reference_images=reference_images,
    )


def _build_image_first_style_profile(asset_inventory: AssetInventory | None) -> StyleProfile:
    image_items = [
        item
        for item in (asset_inventory.items if asset_inventory else [])
        if item.media_kind == "image"
    ]
    if not image_items:
        raise ValueError(
            "No video analyses or image assets were found. Add at least two scene images "
            "under the selected Input project, or add optional videos for style analysis."
        )

    resolution_counts = Counter(
        (item.width or 720, item.height or 1280)
        for item in image_items
    )
    target_width, target_height = resolution_counts.most_common(1)[0][0]

    color_counter: Counter[str] = Counter()
    brightness_values: list[float] = []
    for item in image_items[:24]:
        image = cv2.imread(item.path)
        if image is None:
            continue
        brightness_values.append(float(image.mean() / 255.0))
        pixels = image.reshape(-1, 3)
        if len(pixels) == 0:
            continue
        for index in range(0, len(pixels), max(len(pixels) // 2000, 1)):
            blue, green, red = pixels[index]
            color_counter[_rgb_to_hex(int(red), int(green), int(blue))] += 1

    average_brightness = (
        sum(brightness_values) / len(brightness_values)
        if brightness_values
        else 0.5
    )
    color_palette = [color for color, _ in color_counter.most_common(5)]
    if not color_palette:
        color_palette = ["#d8c7b5", "#101010", "#f2eee8"]

    return StyleProfile(
        source_videos=[],
        target_width=target_width,
        target_height=target_height,
        pacing_label="medium",
        preferred_shot_duration_s=5.0,
        average_brightness=round(average_brightness, 3),
        average_motion=0.0,
        color_palette=color_palette,
        voice_style="voice analysis not available",
        style_summary=(
            "Image-first style profile built from supporting image references. "
            f"Palette led by {', '.join(color_palette[:3])}; no source video motion was analyzed."
        ),
        reference_images=[item.path for item in image_items],
    )


def _rgb_to_hex(red: int, green: int, blue: int) -> str:
    return f"#{red:02x}{green:02x}{blue:02x}"


def load_style_profile(path: Path) -> StyleProfile:
    payload = read_json(path.expanduser().resolve())
    if not isinstance(payload, dict):
        raise ValueError(f"Style profile file must contain a JSON object: {path}")
    return StyleProfile(
        source_videos=[str(item) for item in payload.get("source_videos", [])],
        target_width=int(payload.get("target_width", 1280)),
        target_height=int(payload.get("target_height", 720)),
        pacing_label=str(payload.get("pacing_label", "medium")),
        preferred_shot_duration_s=float(payload.get("preferred_shot_duration_s", 4.0)),
        average_brightness=float(payload.get("average_brightness", 0.5)),
        average_motion=float(payload.get("average_motion", 0.0)),
        color_palette=[str(item) for item in payload.get("color_palette", [])],
        voice_style=str(payload.get("voice_style", "voice analysis not available")),
        style_summary=str(payload.get("style_summary", "")),
        reference_images=[str(item) for item in payload.get("reference_images", [])],
    )
