from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FrameSample:
    timestamp_s: float
    image_path: str
    average_color: str


@dataclass
class AudioProfile:
    detected: bool
    sample_duration_s: float
    mean_level: float
    peak_level: float
    silence_ratio: float
    transcript: str | None = None
    voice_style: str | None = None


@dataclass
class VideoAnalysis:
    video_id: str
    source_path: str
    duration_s: float
    fps: float
    width: int
    height: int
    average_brightness: float
    motion_score: float
    estimated_shot_length_s: float
    color_palette: list[str] = field(default_factory=list)
    sample_frames: list[FrameSample] = field(default_factory=list)
    audio: AudioProfile = field(
        default_factory=lambda: AudioProfile(
            detected=False,
            sample_duration_s=0.0,
            mean_level=0.0,
            peak_level=0.0,
            silence_ratio=1.0,
        )
    )


@dataclass
class StyleProfile:
    source_videos: list[str]
    target_width: int
    target_height: int
    pacing_label: str
    preferred_shot_duration_s: float
    average_brightness: float
    average_motion: float
    color_palette: list[str] = field(default_factory=list)
    voice_style: str = "voice analysis not available"
    style_summary: str = ""
    reference_images: list[str] = field(default_factory=list)


@dataclass
class ShotPlanItem:
    index: int
    title: str
    narration: str
    duration_s: float
    visual_direction: str
    reference_image: str | None = None
    text_overlay: str | None = None
    transition: str = "cut"
    time_start: str | None = None
    time_end: str | None = None
    source_duration: str | None = None
    scene_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class GenerationPlan:
    script: str
    total_duration_s: float
    director_note: str
    items: list[ShotPlanItem] = field(default_factory=list)
    script_format: str = "text"
    script_source_path: str | None = None
    script_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScriptScene:
    name: str
    description: str
    time_start: str | None = None
    time_end: str | None = None
    duration: str | None = None
    duration_s: float | None = None
    text_overlay: str | None = None
    transition: str | None = None
    reference_image: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScriptDocument:
    source_path: str
    format: str
    scenes: list[ScriptScene] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
