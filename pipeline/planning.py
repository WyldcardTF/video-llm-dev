from __future__ import annotations

import re

from .models import GenerationPlan, ScriptDocument, ScriptScene, ShotPlanItem, StyleProfile
from .run_config import PlanningParameters


def plan_from_script(
    script: str | ScriptDocument,
    style_profile: StyleProfile,
    planning: PlanningParameters | None = None,
) -> GenerationPlan:
    planning = planning or PlanningParameters()

    if isinstance(script, ScriptDocument):
        script_document = script
    else:
        script_document = _document_from_text(script)

    if not script_document.scenes:
        raise ValueError("The script is empty.")

    items: list[ShotPlanItem] = []
    reference_images = style_profile.reference_images or [None]

    for index, scene in enumerate(script_document.scenes, start=1):
        description = scene.description.strip()
        words = max(len(description.split()), 1)
        duration_s = _resolve_duration(scene, style_profile, planning, words)
        reference_image = scene.reference_image or reference_images[(index - 1) % len(reference_images)]
        visual_direction = _build_visual_direction(scene, style_profile, planning)

        items.append(
            ShotPlanItem(
                index=index,
                title=scene.name,
                narration=description,
                duration_s=round(duration_s, 2),
                visual_direction=visual_direction,
                reference_image=reference_image,
                text_overlay=scene.text_overlay or _overlay_text(description),
                transition=scene.transition or _default_transition(style_profile, planning),
                time_start=scene.time_start,
                time_end=scene.time_end,
                source_duration=scene.duration,
                scene_metadata=scene.metadata,
            )
        )

    total_duration_s = round(sum(item.duration_s for item in items), 2)
    director_note = (
        f"Use {style_profile.pacing_label} editing, keep colors close to "
        f"{', '.join(style_profile.color_palette[:3])}, preserve the "
        f"{style_profile.voice_style} delivery, and honor the structured scene details."
    )

    script_summary = "\n".join(scene.description for scene in script_document.scenes).strip()
    return GenerationPlan(
        script=script_summary,
        total_duration_s=total_duration_s,
        director_note=director_note,
        items=items,
        script_format=script_document.format,
        script_source_path=script_document.source_path,
        script_metadata=script_document.metadata,
    )


def _document_from_text(script: str) -> ScriptDocument:
    cleaned = script.strip()
    if not cleaned:
        return ScriptDocument(source_path="<inline>", format="text", scenes=[])

    segments = _split_text_script(cleaned)
    scenes = [
        ScriptScene(
            name=f"Scene {index}",
            description=segment,
        )
        for index, segment in enumerate(segments, start=1)
    ]
    return ScriptDocument(
        source_path="<inline>",
        format="text",
        scenes=scenes,
    )


def _split_text_script(script: str) -> list[str]:
    line_based = [line.strip() for line in script.splitlines() if line.strip()]
    if len(line_based) > 1:
        return line_based

    return [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", script) if segment.strip()]


def _estimate_duration(
    word_count: int,
    preferred_shot_duration_s: float,
    pacing_label: str,
    min_duration_s: float,
    max_duration_s: float,
) -> float:
    duration = preferred_shot_duration_s * (word_count / 10.0) ** 0.45
    duration = max(min_duration_s, min(duration, max_duration_s))

    if pacing_label == "fast":
        duration *= 0.85
    elif pacing_label == "slow":
        duration *= 1.15

    return round(duration, 2)


def _build_visual_direction(
    scene: ScriptScene,
    style_profile: StyleProfile,
    planning: PlanningParameters,
) -> str:
    palette = ", ".join(style_profile.color_palette[:3]) or "the reference palette"
    base = (
        f"Frame '{scene.name}' around '{scene.description[:60]}', keep a {style_profile.pacing_label} cadence, "
        f"pull from {palette}, and match the {style_profile.voice_style} tone."
    )

    detail_text = _format_scene_metadata(scene.metadata) if planning.include_scene_metadata_in_prompt else ""
    if detail_text:
        base += f" Scene details: {detail_text}."

    timing_parts = [
        f"start={scene.time_start}" if scene.time_start else None,
        f"end={scene.time_end}" if scene.time_end else None,
        f"duration={scene.duration}" if scene.duration else None,
    ]
    timing_text = ", ".join(part for part in timing_parts if part)
    if timing_text:
        base += f" Timing: {timing_text}."

    return base


def _overlay_text(segment: str) -> str:
    compact = " ".join(segment.split())
    if len(compact) <= 90:
        return compact
    return compact[:87].rstrip() + "..."


def _resolve_duration(
    scene: ScriptScene,
    style_profile: StyleProfile,
    planning: PlanningParameters,
    word_count: int,
) -> float:
    if planning.honor_script_timing and scene.duration_s:
        return max(planning.shot_duration_min_s, min(scene.duration_s, planning.shot_duration_max_s))

    return _estimate_duration(
        word_count,
        style_profile.preferred_shot_duration_s,
        style_profile.pacing_label,
        planning.shot_duration_min_s,
        planning.shot_duration_max_s,
    )


def _default_transition(style_profile: StyleProfile, planning: PlanningParameters) -> str:
    if planning.fallback_transition:
        return planning.fallback_transition
    return "crossfade" if style_profile.pacing_label != "fast" else "cut"


def _format_scene_metadata(metadata: dict[str, object]) -> str:
    if not metadata:
        return ""

    parts: list[str] = []
    for key, value in metadata.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")
    return ", ".join(parts[:6])
