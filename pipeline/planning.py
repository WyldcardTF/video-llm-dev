from __future__ import annotations

import re
from collections import Counter

from .models import (
    AssetCandidate,
    AssetInventory,
    ContinuityProfile,
    GenerationPlan,
    ScriptDocument,
    ScriptScene,
    ShotPlanItem,
    StyleProfile,
)
from .run_config import PlanningParameters


def plan_from_script(
    script: str | ScriptDocument,
    style_profile: StyleProfile,
    planning: PlanningParameters | None = None,
    asset_inventory: AssetInventory | None = None,
    continuity_profile: ContinuityProfile | None = None,
    generation_model: str | None = None,
) -> GenerationPlan:
    planning = planning or PlanningParameters()

    if isinstance(script, ScriptDocument):
        script_document = script
    else:
        script_document = _document_from_text(script)

    if not script_document.scenes:
        raise ValueError("The script is empty.")

    continuity_profile = continuity_profile or build_continuity_profile(script_document, style_profile)
    items: list[ShotPlanItem] = []
    reference_images = style_profile.reference_images or [None]

    for index, scene in enumerate(script_document.scenes, start=1):
        description = scene.description.strip()
        words = max(len(description.split()), 1)
        duration_s = _resolve_duration(scene, style_profile, planning, words)
        selected_asset = _select_asset_for_scene(scene, asset_inventory, index)
        reference_image = _resolve_reference_image(scene, selected_asset, reference_images, index)
        motion_strategy = _motion_strategy_for_asset(selected_asset)
        clip_start_s, clip_duration_s = _resolve_clip_window(scene, selected_asset, duration_s, index)
        continuity_notes = _scene_continuity_notes(scene, continuity_profile)
        visual_direction = _build_visual_direction(
            scene,
            style_profile,
            planning,
            selected_asset=selected_asset,
            continuity_profile=continuity_profile,
        )
        generation_prompt = _build_generation_prompt(
            scene,
            style_profile,
            continuity_profile,
            selected_asset=selected_asset,
            motion_strategy=motion_strategy,
            generation_model=generation_model,
        )

        items.append(
            ShotPlanItem(
                index=index,
                title=scene.name,
                narration=description,
                duration_s=round(duration_s, 2),
                visual_direction=visual_direction,
                reference_image=reference_image,
                source_asset_path=selected_asset.path if selected_asset else reference_image,
                source_asset_type=selected_asset.asset_type if selected_asset else "reference_images",
                media_kind=selected_asset.media_kind if selected_asset else "image",
                clip_start_s=clip_start_s,
                clip_duration_s=clip_duration_s,
                motion_strategy=motion_strategy,
                text_overlay=scene.text_overlay or _overlay_text(description),
                transition=scene.transition or _default_transition(style_profile, planning),
                time_start=scene.time_start,
                time_end=scene.time_end,
                source_duration=scene.duration,
                continuity_notes=continuity_notes,
                generation_prompt=generation_prompt,
                negative_prompt=continuity_profile.negative_prompt,
                scene_metadata=scene.metadata,
            )
        )

    total_duration_s = round(sum(item.duration_s for item in items), 2)
    director_note = (
        f"Use {style_profile.pacing_label} editing, keep colors close to "
        f"{', '.join(style_profile.color_palette[:3])}, preserve the "
        f"{style_profile.voice_style} delivery, and honor the structured scene details."
    )
    continuity_summary = continuity_profile.positive_prompt_prefix

    script_summary = "\n".join(scene.description for scene in script_document.scenes).strip()
    return GenerationPlan(
        script=script_summary,
        total_duration_s=total_duration_s,
        director_note=director_note,
        items=items,
        script_format=script_document.format,
        script_source_path=script_document.source_path,
        continuity_summary=continuity_summary,
        generation_backend="motion_aware_draft",
        script_metadata=script_document.metadata,
    )


def build_continuity_profile(
    script_document: ScriptDocument,
    style_profile: StyleProfile,
) -> ContinuityProfile:
    scenes = script_document.scenes
    subjects = _scene_field_values(scenes, "subject")
    wardrobes = _scene_field_values(scenes, "wardrobe")
    environments = _scene_field_values(scenes, "location", "setting", "environment")
    moods = _scene_field_values(scenes, "mood")

    global_style = script_document.metadata.get("global_style", {})
    if not isinstance(global_style, dict):
        global_style = {}
    project = script_document.metadata.get("project", {})
    if not isinstance(project, dict):
        project = {}

    style_keywords: list[str] = []
    for key in ("mood", "camera_language", "editing_rhythm", "music_direction"):
        value = global_style.get(key)
        if value:
            style_keywords.append(str(value))
    for key in ("objective", "target_audience", "voice_style_goal"):
        value = project.get(key)
        if value:
            style_keywords.append(str(value))

    continuity_rules = [
        "Keep the same lead character identity across shots.",
        "Preserve wardrobe continuity unless the script explicitly changes it.",
        "Keep lighting, grading, and environment treatment inside one shared film world.",
        "Favor smooth temporal motion over sudden visual resets.",
    ]
    if subjects:
        continuity_rules.append(f"Recurring subject continuity: {', '.join(subjects[:3])}.")
    if wardrobes:
        continuity_rules.append(f"Recurring wardrobe continuity: {', '.join(wardrobes[:3])}.")

    subject_text = ", ".join(subjects) or "the same lead subject"
    wardrobe_text = ", ".join(wardrobes) or "consistent wardrobe styling"
    environment_text = ", ".join(environments) or "a consistent environment"
    mood_text = ", ".join(moods[:3]) or style_profile.pacing_label
    style_text = ", ".join(style_keywords[:4]) or style_profile.style_summary

    positive_prompt_prefix = (
        f"Create cinematic moving imagery with {subject_text}, {wardrobe_text}, and {environment_text}. "
        f"Keep the mood around {mood_text}. Match the reference style: {style_text}. "
        f"Maintain temporal consistency, coherent lighting, and believable motion."
    )
    negative_prompt = (
        "Avoid frozen still-frame motion, jitter, flicker, warped faces, extra limbs, "
        "identity drift, costume drift, abrupt background swaps, and inconsistent lighting."
    )

    return ContinuityProfile(
        subjects=subjects,
        wardrobes=wardrobes,
        environments=environments,
        moods=moods,
        style_keywords=style_keywords,
        continuity_rules=continuity_rules,
        positive_prompt_prefix=positive_prompt_prefix,
        negative_prompt=negative_prompt,
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
    selected_asset: AssetCandidate | None,
    continuity_profile: ContinuityProfile,
) -> str:
    palette = ", ".join(style_profile.color_palette[:3]) or "the reference palette"
    base = (
        f"Frame '{scene.name}' around '{scene.description[:60]}', keep a {style_profile.pacing_label} cadence, "
        f"pull from {palette}, and match the {style_profile.voice_style} tone."
    )

    if selected_asset:
        base += (
            f" Use {selected_asset.media_kind} asset '{selected_asset.asset_type}' from {selected_asset.path} "
            f"with a { _motion_strategy_for_asset(selected_asset) } treatment."
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

    if continuity_profile.continuity_rules:
        base += f" Continuity: {' '.join(continuity_profile.continuity_rules[:2])}"

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


def _scene_field_values(scenes: list[ScriptScene], *keys: str) -> list[str]:
    values: list[str] = []
    for scene in scenes:
        for key in keys:
            value = scene.metadata.get(key)
            if value is None:
                continue
            if isinstance(value, list):
                values.extend(str(item) for item in value if str(item).strip())
            else:
                values.append(str(value))
    counts = Counter(item.strip() for item in values if item and item.strip())
    return [value for value, _count in counts.most_common()]


def _select_asset_for_scene(
    scene: ScriptScene,
    asset_inventory: AssetInventory | None,
    index: int,
) -> AssetCandidate | None:
    if asset_inventory is None or not asset_inventory.items:
        return None

    preferred_types = [
        str(item).strip()
        for item in scene.metadata.get("preferred_asset_types", [])
        if str(item).strip()
    ]
    fallback_types = [
        "reference_videos",
        "closeup_videos",
        "broll_videos",
        "testimonials_videos",
        "portraits",
        "product_shots",
        "closeup_images",
        "broll_images",
    ]
    search_types = preferred_types + [item for item in fallback_types if item not in preferred_types]

    for asset_type in search_types:
        candidates = [
            item
            for item in asset_inventory.items
            if item.asset_type == asset_type
        ]
        if not candidates:
            continue

        video_candidates = [item for item in candidates if item.media_kind == "video"]
        if video_candidates:
            return video_candidates[(index - 1) % len(video_candidates)]
        return candidates[(index - 1) % len(candidates)]

    video_candidates = [item for item in asset_inventory.items if item.media_kind == "video"]
    if video_candidates:
        return video_candidates[(index - 1) % len(video_candidates)]

    return asset_inventory.items[(index - 1) % len(asset_inventory.items)]


def _resolve_reference_image(
    scene: ScriptScene,
    selected_asset: AssetCandidate | None,
    reference_images: list[str | None],
    index: int,
) -> str | None:
    if scene.reference_image:
        return scene.reference_image
    if selected_asset and selected_asset.media_kind == "image":
        return selected_asset.path
    return reference_images[(index - 1) % len(reference_images)]


def _motion_strategy_for_asset(selected_asset: AssetCandidate | None) -> str:
    if selected_asset is None:
        return "still_pan"
    if selected_asset.media_kind == "video":
        return "source_video_excerpt"
    return "still_parallax"


def _scene_continuity_notes(scene: ScriptScene, continuity_profile: ContinuityProfile) -> list[str]:
    notes: list[str] = []
    for key in ("subject", "wardrobe", "mood", "location", "environment", "setting"):
        value = scene.metadata.get(key)
        if value:
            notes.append(f"{key}={value}")
    notes.extend(continuity_profile.continuity_rules[:2])
    return notes[:6]


def _build_generation_prompt(
    scene: ScriptScene,
    style_profile: StyleProfile,
    continuity_profile: ContinuityProfile,
    selected_asset: AssetCandidate | None,
    motion_strategy: str,
    generation_model: str | None,
) -> str:
    asset_text = "no explicit asset selection"
    if selected_asset is not None:
        asset_text = (
            f"use the {selected_asset.asset_type} {selected_asset.media_kind} asset at {selected_asset.path}"
        )

    scene_detail = _format_scene_metadata(scene.metadata)
    prompt = (
        f"{continuity_profile.positive_prompt_prefix} "
        f"Scene: {scene.name}. Action: {scene.description}. "
        f"Motion strategy: {motion_strategy}. Asset guidance: {asset_text}. "
        f"Target pacing: {style_profile.pacing_label}. Voice tone: {style_profile.voice_style}. "
    )
    if scene_detail:
        prompt += f"Scene metadata: {scene_detail}. "
    if generation_model:
        prompt += f"Intended downstream generation model: {generation_model}. "
    return prompt.strip()


def _resolve_clip_window(
    scene: ScriptScene,
    selected_asset: AssetCandidate | None,
    duration_s: float,
    index: int,
) -> tuple[float | None, float | None]:
    if selected_asset is None or selected_asset.media_kind != "video":
        return None, None

    asset_duration = selected_asset.duration_s or duration_s
    if asset_duration <= 0:
        return None, round(duration_s, 2)

    clip_duration_s = min(duration_s, asset_duration)
    time_start_s = _timestamp_to_seconds(scene.time_start)
    if time_start_s is not None:
        start_s = min(max(time_start_s, 0.0), max(asset_duration - clip_duration_s, 0.0))
        return round(start_s, 2), round(clip_duration_s, 2)

    available = max(asset_duration - clip_duration_s, 0.0)
    if available <= 0:
        return 0.0, round(clip_duration_s, 2)

    start_s = (available * ((index - 1) % 5)) / max(4, 1)
    return round(start_s, 2), round(clip_duration_s, 2)


def _timestamp_to_seconds(value: str | None) -> float | None:
    if not value:
        return None

    cleaned = value.strip()
    if not cleaned:
        return None

    labeled_match = re.fullmatch(
        r"(?:(?P<h>\d+)h:)?(?:(?P<m>\d+)m:)?(?:(?P<s>\d+)s:)?(?:(?P<ms>\d+)ms)?",
        cleaned,
    )
    if labeled_match:
        hours = int(labeled_match.group("h") or 0)
        minutes = int(labeled_match.group("m") or 0)
        seconds = int(labeled_match.group("s") or 0)
        milliseconds = int(labeled_match.group("ms") or 0)
        return hours * 3600 + minutes * 60 + seconds + (milliseconds / 1000.0)

    colon_match = re.fullmatch(r"(?P<h>\d+):(?P<m>\d+):(?P<s>\d+)(?:\.(?P<ms>\d+))?", cleaned)
    if colon_match:
        hours = int(colon_match.group("h") or 0)
        minutes = int(colon_match.group("m") or 0)
        seconds = int(colon_match.group("s") or 0)
        milliseconds = int((colon_match.group("ms") or "0").ljust(3, "0")[:3])
        return hours * 3600 + minutes * 60 + seconds + (milliseconds / 1000.0)

    try:
        return float(cleaned)
    except ValueError:
        return None
