from __future__ import annotations

import re

from .models import GenerationPlan, ShotPlanItem, StyleProfile


def plan_from_script(script: str, style_profile: StyleProfile) -> GenerationPlan:
    segments = _split_script(script)
    if not segments:
        raise ValueError("The script is empty.")

    items: list[ShotPlanItem] = []
    reference_images = style_profile.reference_images or [None]

    for index, segment in enumerate(segments, start=1):
        words = max(len(segment.split()), 1)
        duration_s = _estimate_duration(words, style_profile.preferred_shot_duration_s, style_profile.pacing_label)
        reference_image = reference_images[(index - 1) % len(reference_images)]
        visual_direction = _build_visual_direction(segment, style_profile)

        items.append(
            ShotPlanItem(
                index=index,
                narration=segment,
                duration_s=duration_s,
                visual_direction=visual_direction,
                reference_image=reference_image,
                text_overlay=_overlay_text(segment),
                transition="crossfade" if style_profile.pacing_label != "fast" else "cut",
            )
        )

    total_duration_s = round(sum(item.duration_s for item in items), 2)
    director_note = (
        f"Use {style_profile.pacing_label} editing, keep colors close to "
        f"{', '.join(style_profile.color_palette[:3])}, and preserve the "
        f"{style_profile.voice_style} delivery."
    )

    return GenerationPlan(
        script=script.strip(),
        total_duration_s=total_duration_s,
        director_note=director_note,
        items=items,
    )


def _split_script(script: str) -> list[str]:
    cleaned = script.strip()
    if not cleaned:
        return []

    line_based = [line.strip() for line in cleaned.splitlines() if line.strip()]
    if len(line_based) > 1:
        return line_based

    return [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", cleaned) if segment.strip()]


def _estimate_duration(word_count: int, preferred_shot_duration_s: float, pacing_label: str) -> float:
    duration = preferred_shot_duration_s * (word_count / 10.0) ** 0.45
    duration = max(2.0, min(duration, 7.5))

    if pacing_label == "fast":
        duration *= 0.85
    elif pacing_label == "slow":
        duration *= 1.15

    return round(duration, 2)


def _build_visual_direction(segment: str, style_profile: StyleProfile) -> str:
    palette = ", ".join(style_profile.color_palette[:3]) or "the reference palette"
    return (
        f"Frame this beat around '{segment[:60]}', keep a {style_profile.pacing_label} cadence, "
        f"pull from {palette}, and match the {style_profile.voice_style} tone."
    )


def _overlay_text(segment: str) -> str:
    compact = " ".join(segment.split())
    if len(compact) <= 90:
        return compact
    return compact[:87].rstrip() + "..."
