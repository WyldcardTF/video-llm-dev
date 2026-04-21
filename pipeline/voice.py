from __future__ import annotations

import re


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
