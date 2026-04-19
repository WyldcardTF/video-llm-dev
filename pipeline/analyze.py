from __future__ import annotations

import subprocess
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

from .config import get_settings
from .io_utils import ensure_dir, slugify
from .models import AudioProfile, FrameSample, VideoAnalysis
from .voice import describe_voice_style, maybe_transcribe_video


class VideoAnalyzer:
    def __init__(
        self,
        sample_frames: int | None = None,
        timeline_scan_points: int | None = None,
        transcribe_voice: bool | None = None,
        frames_dir_name: str | None = None,
        audio_dir_name: str | None = None,
        audio_analysis_max_seconds: int | None = None,
        transcription_max_seconds: int | None = None,
        openai_api_key: str | None = None,
        openai_transcribe_model: str | None = None,
    ) -> None:
        settings = get_settings()
        resolved_sample_frames = 6 if sample_frames is None else sample_frames
        resolved_timeline_scan_points = 48 if timeline_scan_points is None else timeline_scan_points

        self.sample_frames = max(resolved_sample_frames, 3)
        self.timeline_scan_points = max(resolved_timeline_scan_points, 12)
        self.transcribe_voice = False if transcribe_voice is None else transcribe_voice
        self.frames_dir_name = settings.frames_dir_name if frames_dir_name is None else frames_dir_name
        self.audio_dir_name = settings.audio_dir_name if audio_dir_name is None else audio_dir_name
        self.audio_analysis_max_seconds = (
            90 if audio_analysis_max_seconds is None else audio_analysis_max_seconds
        )
        self.transcription_max_seconds = (
            60 if transcription_max_seconds is None else transcription_max_seconds
        )
        self.openai_api_key = settings.openai_api_key if openai_api_key is None else openai_api_key
        self.openai_transcribe_model = (
            "whisper-1" if openai_transcribe_model is None else openai_transcribe_model
        )

    def analyze_many(self, video_paths: list[Path], project_dir: Path) -> list[VideoAnalysis]:
        return [self.analyze_video(video_path, project_dir) for video_path in video_paths]

    def analyze_video(self, video_path: Path, project_dir: Path) -> VideoAnalysis:
        video_id = slugify(video_path.stem)
        frames_dir = ensure_dir(project_dir / self.frames_dir_name / video_id)
        audio_dir = ensure_dir(project_dir / self.audio_dir_name)

        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")

        fps = capture.get(cv2.CAP_PROP_FPS) or 24.0
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 1280)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 720)
        duration_s = frame_count / fps if frame_count > 0 and fps > 0 else 0.0

        sample_frames = self._extract_sample_frames(
            capture=capture,
            video_id=video_id,
            frames_dir=frames_dir,
            duration_s=duration_s,
            fps=fps,
            frame_count=frame_count,
        )
        average_brightness = self._estimate_brightness(sample_frames)
        motion_score, estimated_shot_length_s = self._estimate_motion_and_pacing(
            capture=capture,
            duration_s=duration_s,
            fps=fps,
            frame_count=frame_count,
        )
        capture.release()

        audio_profile = self._analyze_audio(video_path, audio_dir)
        color_palette = self._extract_palette(sample_frames)

        return VideoAnalysis(
            video_id=video_id,
            source_path=str(video_path),
            duration_s=round(duration_s, 2),
            fps=round(fps, 2),
            width=width,
            height=height,
            average_brightness=round(average_brightness, 3),
            motion_score=round(motion_score, 3),
            estimated_shot_length_s=round(estimated_shot_length_s, 2),
            color_palette=color_palette,
            sample_frames=sample_frames,
            audio=audio_profile,
        )

    def _extract_sample_frames(
        self,
        capture: cv2.VideoCapture,
        video_id: str,
        frames_dir: Path,
        duration_s: float,
        fps: float,
        frame_count: int,
    ) -> list[FrameSample]:
        if duration_s <= 0 or frame_count <= 0:
            return []

        timestamps = np.linspace(
            max(duration_s * 0.05, 0.0),
            max(duration_s * 0.95, 0.0),
            num=self.sample_frames,
        )

        frames: list[FrameSample] = []
        for index, timestamp_s in enumerate(timestamps, start=1):
            frame_index = min(int(timestamp_s * fps), max(frame_count - 1, 0))
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            success, frame = capture.read()
            if not success or frame is None:
                continue

            image_path = frames_dir / f"{video_id}_{index:02d}.jpg"
            cv2.imwrite(str(image_path), frame)

            average_color = self._bgr_to_hex(frame.mean(axis=(0, 1)))
            frames.append(
                FrameSample(
                    timestamp_s=round(float(timestamp_s), 2),
                    image_path=str(image_path),
                    average_color=average_color,
                )
            )
        return frames

    def _estimate_brightness(self, sample_frames: list[FrameSample]) -> float:
        brightness_values: list[float] = []
        for sample in sample_frames:
            frame = cv2.imread(sample.image_path)
            if frame is None:
                continue
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            brightness_values.append(float(gray.mean() / 255.0))
        if not brightness_values:
            return 0.5
        return float(np.mean(brightness_values))

    def _estimate_motion_and_pacing(
        self,
        capture: cv2.VideoCapture,
        duration_s: float,
        fps: float,
        frame_count: int,
    ) -> tuple[float, float]:
        if duration_s <= 0 or frame_count <= 0:
            return 0.0, 3.0

        scan_points = min(self.timeline_scan_points, max(frame_count, 1))
        timestamps = np.linspace(0.0, max(duration_s - (1.0 / max(fps, 1.0)), 0.0), num=scan_points)

        previous_frame: np.ndarray | None = None
        diffs: list[float] = []

        for timestamp_s in timestamps:
            frame_index = min(int(timestamp_s * fps), max(frame_count - 1, 0))
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            success, frame = capture.read()
            if not success or frame is None:
                continue

            gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray_frame = cv2.resize(gray_frame, (160, 90))

            if previous_frame is not None:
                diff = np.mean(np.abs(gray_frame.astype(np.float32) - previous_frame.astype(np.float32))) / 255.0
                diffs.append(float(diff))
            previous_frame = gray_frame

        if not diffs:
            return 0.0, max(duration_s, 1.0)

        motion_score = float(np.mean(diffs))
        threshold = float(np.mean(diffs) + (0.75 * np.std(diffs)))
        cut_count = sum(diff > threshold for diff in diffs)
        estimated_shot_length_s = duration_s / max(cut_count + 1, 1)
        return motion_score, estimated_shot_length_s

    def _extract_palette(self, sample_frames: list[FrameSample]) -> list[str]:
        bins: Counter[tuple[int, int, int]] = Counter()

        for sample in sample_frames:
            frame = cv2.imread(sample.image_path)
            if frame is None:
                continue

            resized = cv2.resize(frame, (32, 32))
            flat_pixels = resized.reshape(-1, 3)
            quantized = ((flat_pixels // 32) * 32) + 16
            for blue, green, red in quantized:
                bins[(int(red), int(green), int(blue))] += 1

        if not bins:
            return ["#4A4A4A", "#BFBFBF"]

        top_colors = [self._rgb_to_hex(color) for color, _ in bins.most_common(5)]
        return top_colors

    def _analyze_audio(self, video_path: Path, audio_dir: Path) -> AudioProfile:
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(video_path),
            "-t",
            str(self.audio_analysis_max_seconds),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "s16le",
            "-",
        ]

        process = subprocess.run(command, capture_output=True, check=False)
        if process.returncode != 0 or not process.stdout:
            return AudioProfile(
                detected=False,
                sample_duration_s=0.0,
                mean_level=0.0,
                peak_level=0.0,
                silence_ratio=1.0,
                voice_style="no audio track detected",
            )

        signal = np.frombuffer(process.stdout, dtype=np.int16).astype(np.float32) / 32768.0
        if signal.size == 0:
            return AudioProfile(
                detected=False,
                sample_duration_s=0.0,
                mean_level=0.0,
                peak_level=0.0,
                silence_ratio=1.0,
                voice_style="no audio track detected",
            )

        transcript = None
        if self.transcribe_voice:
            try:
                transcript = maybe_transcribe_video(
                    video_path,
                    audio_dir,
                    api_key=self.openai_api_key,
                    model_name=self.openai_transcribe_model,
                    max_seconds=self.transcription_max_seconds,
                )
            except Exception:
                transcript = None

        mean_level = float(np.mean(np.abs(signal)))
        peak_level = float(np.max(np.abs(signal)))
        silence_ratio = float(np.mean(np.abs(signal) < 0.02))
        voice_style = describe_voice_style(
            mean_level=mean_level,
            peak_level=peak_level,
            silence_ratio=silence_ratio,
            transcript=transcript,
        )

        return AudioProfile(
            detected=True,
            sample_duration_s=round(signal.size / 16000.0, 2),
            mean_level=round(mean_level, 3),
            peak_level=round(peak_level, 3),
            silence_ratio=round(silence_ratio, 3),
            transcript=transcript,
            voice_style=voice_style,
        )

    @staticmethod
    def _rgb_to_hex(color: tuple[int, int, int]) -> str:
        red, green, blue = color
        return f"#{red:02X}{green:02X}{blue:02X}"

    @staticmethod
    def _bgr_to_hex(color: np.ndarray) -> str:
        blue, green, red = [int(channel) for channel in color]
        return f"#{red:02X}{green:02X}{blue:02X}"
