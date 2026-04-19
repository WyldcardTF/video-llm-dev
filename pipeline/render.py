from __future__ import annotations

import subprocess
import textwrap
from collections import deque
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .ingest import VIDEO_EXTENSIONS
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
    silent_output = (
        output_path
        if voiceover_path is None
        else output_path.with_name(f"{output_path.stem}_silent{output_path.suffix}")
    )

    frame_size = (style_profile.target_width, style_profile.target_height)
    writer = cv2.VideoWriter(
        str(silent_output),
        cv2.VideoWriter_fourcc(*"mp4v"),
        resolved_fps,
        frame_size,
    )
    if not writer.isOpened():
        raise RuntimeError(f"Could not create output video: {silent_output}")

    previous_tail: list[np.ndarray] = []
    previous_transition = "cut"

    for index, item in enumerate(plan.items):
        frame_iter = _iter_rendered_shot_frames(
            item=item,
            style_profile=style_profile,
            frame_size=frame_size,
            fps=resolved_fps,
        )

        incoming_transition = previous_transition if previous_tail else "cut"
        incoming_transition_frames = _transition_frame_count(
            incoming_transition,
            resolved_fps,
        )
        current_head = _take_frames(frame_iter, incoming_transition_frames)

        _write_transition(
            writer=writer,
            previous_tail=previous_tail,
            current_head=current_head,
            transition=incoming_transition,
        )

        outgoing_transition_frames = (
            _transition_frame_count(item.transition, resolved_fps)
            if index < len(plan.items) - 1
            else 0
        )

        previous_tail = _write_stream_with_tail_buffer(
            writer=writer,
            frame_iter=frame_iter,
            tail_size=outgoing_transition_frames,
        )
        previous_transition = item.transition

    for frame in previous_tail:
        _write_rgb_frame(writer, frame)

    writer.release()

    if voiceover_path is None:
        return silent_output

    muxed_output = output_path
    _mux_audio_track(silent_output, voiceover_path, muxed_output)
    return muxed_output


def _iter_rendered_shot_frames(
    item: ShotPlanItem,
    style_profile: StyleProfile,
    frame_size: tuple[int, int],
    fps: int,
) -> Iterator[np.ndarray]:
    total_frames = max(int(round(item.duration_s * fps)), 1)

    if item.media_kind == "video" and item.source_asset_path:
        yield from _iter_video_frames(
            item=item,
            style_profile=style_profile,
            frame_size=frame_size,
            fps=fps,
            total_frames=total_frames,
        )
        return

    background = _load_background(item, style_profile, frame_size)
    for frame_index in range(total_frames):
        progress = frame_index / max(total_frames - 1, 1)
        animated = _apply_still_motion(background, progress, item.index)
        graded = _apply_grade(animated, style_profile)
        composited = _draw_overlay(graded, item, style_profile)
        yield composited


def _iter_video_frames(
    item: ShotPlanItem,
    style_profile: StyleProfile,
    frame_size: tuple[int, int],
    fps: int,
    total_frames: int,
) -> Iterator[np.ndarray]:
    video_path = Path(item.source_asset_path).expanduser().resolve()
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        fallback = _load_background(item, style_profile, frame_size)
        for frame_index in range(total_frames):
            progress = frame_index / max(total_frames - 1, 1)
            animated = _apply_still_motion(fallback, progress, item.index)
            graded = _apply_grade(animated, style_profile)
            yield _draw_overlay(graded, item, style_profile)
        return

    source_fps = capture.get(cv2.CAP_PROP_FPS) or float(fps)
    source_frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    source_duration_s = (
        source_frame_count / source_fps
        if source_frame_count > 0 and source_fps > 0
        else max(item.clip_duration_s or item.duration_s, item.duration_s)
    )
    clip_start_s = max(item.clip_start_s or 0.0, 0.0)
    clip_duration_s = min(item.clip_duration_s or item.duration_s, max(source_duration_s - clip_start_s, 0.04))
    clip_duration_s = max(clip_duration_s, 0.04)

    last_good_frame: np.ndarray | None = None
    for frame_index in range(total_frames):
        progress = frame_index / max(total_frames - 1, 1)
        source_time_s = clip_start_s + (progress * clip_duration_s)
        frame_number = min(
            int(round(source_time_s * source_fps)),
            max(source_frame_count - 1, 0),
        )
        capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
        success, frame = capture.read()

        if success and frame is not None:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            last_good_frame = _cover_resize(rgb_frame, frame_size[0], frame_size[1])
        elif last_good_frame is None:
            last_good_frame = _load_background(item, style_profile, frame_size)

        animated = _apply_video_motion(last_good_frame, progress, item.index)
        graded = _apply_grade(animated, style_profile)
        yield _draw_overlay(graded, item, style_profile)

    capture.release()


def _load_background(item: ShotPlanItem, style_profile: StyleProfile, frame_size: tuple[int, int]) -> np.ndarray:
    width, height = frame_size

    candidate_paths = [
        item.source_asset_path,
        item.reference_image,
    ]
    for candidate_path in candidate_paths:
        if not candidate_path:
            continue
        path = Path(candidate_path).expanduser().resolve()
        suffix = path.suffix.lower()
        if suffix in VIDEO_EXTENSIONS:
            frame = _load_video_cover_frame(path)
            if frame is not None:
                return _cover_resize(frame, width, height)
            continue

        source = cv2.imread(str(path))
        if source is not None:
            rgb_source = cv2.cvtColor(source, cv2.COLOR_BGR2RGB)
            return _cover_resize(rgb_source, width, height)

    fallback_color = _hex_to_rgb(style_profile.color_palette[0] if style_profile.color_palette else "#404040")
    return np.full((height, width, 3), fallback_color, dtype=np.uint8)


def _load_video_cover_frame(path: Path) -> np.ndarray | None:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return None

    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    midpoint = max(frame_count // 2, 0)
    capture.set(cv2.CAP_PROP_POS_FRAMES, midpoint)
    success, frame = capture.read()
    capture.release()
    if not success or frame is None:
        return None
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def _cover_resize(image: np.ndarray, width: int, height: int) -> np.ndarray:
    source_height, source_width = image.shape[:2]
    scale = max(width / max(source_width, 1), height / max(source_height, 1))
    resized = cv2.resize(image, (int(source_width * scale), int(source_height * scale)))

    offset_x = max((resized.shape[1] - width) // 2, 0)
    offset_y = max((resized.shape[0] - height) // 2, 0)
    return resized[offset_y:offset_y + height, offset_x:offset_x + width]


def _apply_still_motion(image: np.ndarray, progress: float, shot_index: int) -> np.ndarray:
    height, width = image.shape[:2]
    zoom = 1.04 + (0.05 * progress)
    enlarged = cv2.resize(image, (int(width * zoom), int(height * zoom)))

    x_span = max(enlarged.shape[1] - width, 0)
    y_span = max(enlarged.shape[0] - height, 0)
    x_direction = progress if shot_index % 2 == 0 else 1.0 - progress
    offset_x = int(x_span * x_direction)
    offset_y = int(y_span * 0.35 * progress)

    return enlarged[offset_y:offset_y + height, offset_x:offset_x + width]


def _apply_video_motion(image: np.ndarray, progress: float, shot_index: int) -> np.ndarray:
    height, width = image.shape[:2]
    zoom = 1.01 + (0.015 * np.sin(progress * np.pi))
    enlarged = cv2.resize(image, (int(width * zoom), int(height * zoom)))

    x_span = max(enlarged.shape[1] - width, 0)
    y_span = max(enlarged.shape[0] - height, 0)
    x_direction = progress if shot_index % 2 == 0 else 1.0 - progress
    offset_x = int(x_span * 0.4 * x_direction)
    offset_y = int(y_span * 0.2 * (1.0 - progress))

    return enlarged[offset_y:offset_y + height, offset_x:offset_x + width]


def _apply_grade(image: np.ndarray, style_profile: StyleProfile) -> np.ndarray:
    graded = cv2.convertScaleAbs(image, alpha=1.06, beta=4)
    accent_color = np.array(
        _hex_to_rgb(style_profile.color_palette[1] if len(style_profile.color_palette) > 1 else "#C8C8C8"),
        dtype=np.float32,
    )
    graded = np.clip((graded.astype(np.float32) * 0.94) + (accent_color * 0.06), 0, 255).astype(np.uint8)

    height, width = graded.shape[:2]
    x_kernel = cv2.getGaussianKernel(width, width * 0.45)
    y_kernel = cv2.getGaussianKernel(height, height * 0.45)
    vignette = y_kernel @ x_kernel.T
    vignette = vignette / np.max(vignette)
    vignette = (0.85 + (0.15 * vignette)).astype(np.float32)
    return np.clip(graded.astype(np.float32) * vignette[..., None], 0, 255).astype(np.uint8)


def _draw_overlay(image: np.ndarray, item: ShotPlanItem, style_profile: StyleProfile) -> np.ndarray:
    if not item.text_overlay and not item.title:
        return image

    canvas = Image.fromarray(image)
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    width, height = canvas.size
    panel_height = int(height * 0.16)
    panel_top = height - panel_height - 28
    panel_left = 28
    panel_right = width - 28
    panel_bottom = height - 28

    draw.rounded_rectangle(
        [(panel_left, panel_top), (panel_right, panel_bottom)],
        radius=26,
        fill=(10, 10, 10, 128),
    )

    accent = _hex_to_rgb(style_profile.color_palette[1] if len(style_profile.color_palette) > 1 else "#E6E6E6")
    draw.rectangle(
        [(panel_left + 18, panel_top + 18), (panel_left + 24, panel_bottom - 18)],
        fill=(*accent, 255),
    )

    title_font = _load_font(28, bold=True)
    body_font = _load_font(22)

    title = item.title or f"Shot {item.index}"
    copy = textwrap.fill(item.text_overlay or item.narration, width=52)

    draw.text((panel_left + 42, panel_top + 16), title, font=title_font, fill=(255, 255, 255, 235))
    draw.multiline_text(
        (panel_left + 42, panel_top + 52),
        copy,
        font=body_font,
        fill=(245, 245, 245, 230),
        spacing=6,
    )

    composited = Image.alpha_composite(canvas.convert("RGBA"), overlay)
    return np.array(composited.convert("RGB"))


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _transition_frame_count(transition: str, fps: int) -> int:
    normalized = (transition or "").strip().lower()
    if normalized in {"crossfade", "fade", "dissolve"}:
        return max(int(round(fps * 0.33)), 1)
    return 0


def _take_frames(frame_iter: Iterator[np.ndarray], limit: int) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    for _ in range(limit):
        try:
            frames.append(next(frame_iter))
        except StopIteration:
            break
    return frames


def _write_stream_with_tail_buffer(
    writer: cv2.VideoWriter,
    frame_iter: Iterator[np.ndarray],
    tail_size: int,
) -> list[np.ndarray]:
    if tail_size <= 0:
        for frame in frame_iter:
            _write_rgb_frame(writer, frame)
        return []

    buffer: deque[np.ndarray] = deque()
    for frame in frame_iter:
        buffer.append(frame)
        if len(buffer) > tail_size:
            _write_rgb_frame(writer, buffer.popleft())
    return list(buffer)


def _write_transition(
    writer: cv2.VideoWriter,
    previous_tail: list[np.ndarray],
    current_head: list[np.ndarray],
    transition: str,
) -> None:
    if not previous_tail:
        for frame in current_head:
            _write_rgb_frame(writer, frame)
        return

    normalized = (transition or "").strip().lower()
    if normalized not in {"crossfade", "fade", "dissolve"}:
        for frame in previous_tail:
            _write_rgb_frame(writer, frame)
        for frame in current_head:
            _write_rgb_frame(writer, frame)
        return

    blend_count = min(len(previous_tail), len(current_head))
    if blend_count <= 0:
        for frame in previous_tail:
            _write_rgb_frame(writer, frame)
        for frame in current_head:
            _write_rgb_frame(writer, frame)
        return

    for frame in previous_tail[:-blend_count]:
        _write_rgb_frame(writer, frame)

    for index in range(blend_count):
        alpha = (index + 1) / blend_count
        if normalized == "fade":
            black = np.zeros_like(previous_tail[-blend_count + index])
            faded_prev = cv2.addWeighted(previous_tail[-blend_count + index], 1.0 - alpha, black, alpha, 0)
            blended = cv2.addWeighted(faded_prev, 1.0 - alpha, current_head[index], alpha, 0)
        else:
            blended = cv2.addWeighted(
                previous_tail[-blend_count + index],
                1.0 - alpha,
                current_head[index],
                alpha,
                0,
            )
        _write_rgb_frame(writer, blended)

    for frame in current_head[blend_count:]:
        _write_rgb_frame(writer, frame)


def _write_rgb_frame(writer: cv2.VideoWriter, frame: np.ndarray) -> None:
    writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))


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
