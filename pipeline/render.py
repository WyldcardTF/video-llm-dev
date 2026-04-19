from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .models import GenerationPlan, ShotPlanItem, StyleProfile


def render_plan(
    plan: GenerationPlan,
    style_profile: StyleProfile,
    output_path: Path,
    fps: int | None = None,
    voiceover_path: Path | None = None,
) -> Path:
    resolved_fps = 24 if fps is None else fps

    output_path.parent.mkdir(parents=True, exist_ok=True)
    silent_output = output_path if voiceover_path is None else output_path.with_name(f"{output_path.stem}_silent{output_path.suffix}")

    frame_size = (style_profile.target_width, style_profile.target_height)
    writer = cv2.VideoWriter(
        str(silent_output),
        cv2.VideoWriter_fourcc(*"mp4v"),
        resolved_fps,
        frame_size,
    )
    if not writer.isOpened():
        raise RuntimeError(f"Could not create output video: {silent_output}")

    for item in plan.items:
        background = _load_background(item, style_profile, frame_size)
        frame_total = max(int(round(item.duration_s * resolved_fps)), 1)

        for frame_index in range(frame_total):
            progress = frame_index / max(frame_total - 1, 1)
            animated = _apply_motion(background, progress, item.index)
            composited = _draw_overlay(animated, item, style_profile)
            writer.write(cv2.cvtColor(composited, cv2.COLOR_RGB2BGR))

    writer.release()

    if voiceover_path is None:
        return silent_output

    muxed_output = output_path
    _mux_audio_track(silent_output, voiceover_path, muxed_output)
    return muxed_output


def _load_background(item: ShotPlanItem, style_profile: StyleProfile, frame_size: tuple[int, int]) -> np.ndarray:
    width, height = frame_size

    if item.reference_image:
        source = cv2.imread(item.reference_image)
        if source is not None:
            rgb_source = cv2.cvtColor(source, cv2.COLOR_BGR2RGB)
            return _cover_resize(rgb_source, width, height)

    fallback_color = _hex_to_rgb(style_profile.color_palette[0] if style_profile.color_palette else "#404040")
    return np.full((height, width, 3), fallback_color, dtype=np.uint8)


def _cover_resize(image: np.ndarray, width: int, height: int) -> np.ndarray:
    source_height, source_width = image.shape[:2]
    scale = max(width / max(source_width, 1), height / max(source_height, 1))
    resized = cv2.resize(image, (int(source_width * scale), int(source_height * scale)))

    offset_x = max((resized.shape[1] - width) // 2, 0)
    offset_y = max((resized.shape[0] - height) // 2, 0)
    return resized[offset_y:offset_y + height, offset_x:offset_x + width]


def _apply_motion(image: np.ndarray, progress: float, shot_index: int) -> np.ndarray:
    height, width = image.shape[:2]
    zoom = 1.06 + (0.04 * progress)
    enlarged = cv2.resize(image, (int(width * zoom), int(height * zoom)))

    x_span = max(enlarged.shape[1] - width, 0)
    y_span = max(enlarged.shape[0] - height, 0)

    if shot_index % 2 == 0:
        offset_x = int(x_span * progress)
    else:
        offset_x = int(x_span * (1.0 - progress))
    offset_y = int(y_span * 0.5 * progress)

    return enlarged[offset_y:offset_y + height, offset_x:offset_x + width]


def _draw_overlay(image: np.ndarray, item: ShotPlanItem, style_profile: StyleProfile) -> np.ndarray:
    canvas = Image.fromarray(image)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    width, height = canvas.size
    panel_height = int(height * 0.28)
    panel_top = height - panel_height - 24
    panel_left = 24
    panel_right = width - 24
    panel_bottom = height - 24

    draw.rounded_rectangle(
        [(panel_left, panel_top), (panel_right, panel_bottom)],
        radius=28,
        fill=(12, 12, 12, 168),
    )

    accent = _hex_to_rgb(style_profile.color_palette[1] if len(style_profile.color_palette) > 1 else "#E6E6E6")
    draw.rectangle(
        [(panel_left + 16, panel_top + 18), (panel_left + 24, panel_bottom - 18)],
        fill=(*accent, 255),
    )

    title_font = _load_font(42, bold=True)
    body_font = _load_font(30)

    title = item.title or f"Shot {item.index}"
    copy = textwrap.fill(item.text_overlay or item.narration, width=42)

    draw.text((panel_left + 46, panel_top + 22), title, font=title_font, fill=(255, 255, 255, 255))
    draw.multiline_text(
        (panel_left + 46, panel_top + 82),
        copy,
        font=body_font,
        fill=(245, 245, 245, 255),
        spacing=8,
    )

    composited = Image.alpha_composite(canvas.convert("RGBA"), overlay)
    return np.array(composited.convert("RGB"))


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    cleaned = hex_color.lstrip("#")
    return tuple(int(cleaned[index:index + 2], 16) for index in (0, 2, 4))


def _mux_audio_track(video_path: Path, audio_path: Path, output_path: Path) -> None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(audio_path),
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        str(output_path),
    ]
    subprocess.run(command, check=True, capture_output=True)
