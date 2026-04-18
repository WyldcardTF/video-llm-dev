from __future__ import annotations

from collections import Counter

from .models import StyleProfile, VideoAnalysis


def build_style_profile(analyses: list[VideoAnalysis]) -> StyleProfile:
    if not analyses:
        raise ValueError("At least one video analysis is required to build a style profile.")

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
