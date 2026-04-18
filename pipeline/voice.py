from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .io_utils import ensure_dir


def maybe_transcribe_video(video_path: Path, audio_dir: Path, max_seconds: int = 60) -> str | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    ensure_dir(audio_dir)
    sample_path = audio_dir / f"{video_path.stem}_voice_sample.mp3"

    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(video_path),
        "-t",
        str(max_seconds),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-q:a",
        "4",
        str(sample_path),
    ]
    subprocess.run(command, check=True, capture_output=True)

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model_name = os.getenv("OPENAI_TRANSCRIBE_MODEL", "whisper-1")

    with sample_path.open("rb") as audio_handle:
        transcript = client.audio.transcriptions.create(
            model=model_name,
            file=audio_handle,
        )

    text = getattr(transcript, "text", None)
    if text:
        return text.strip() or None
    return None


def describe_voice_style(
    mean_level: float,
    peak_level: float,
    silence_ratio: float,
    transcript: str | None = None,
) -> str:
    if mean_level < 0.03 and peak_level < 0.08:
        energy = "soft-spoken"
    elif mean_level < 0.08:
        energy = "balanced"
    else:
        energy = "energetic"

    if silence_ratio > 0.65:
        pacing = "measured"
    elif silence_ratio > 0.4:
        pacing = "steady"
    else:
        pacing = "fast-moving"

    phrasing = "direct"
    if transcript:
        sentences = [segment.strip() for segment in re.split(r"[.!?]+", transcript) if segment.strip()]
        word_count = len(transcript.split())
        average_sentence_length = word_count / max(len(sentences), 1)

        if average_sentence_length >= 18:
            phrasing = "storytelling"
        elif average_sentence_length >= 11:
            phrasing = "conversational"

        if "!" in transcript:
            energy = "punchy"

    return f"{energy}, {pacing}, {phrasing} voice"
