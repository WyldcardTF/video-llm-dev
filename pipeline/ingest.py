from __future__ import annotations

from pathlib import Path


VIDEO_EXTENSIONS = {
    ".avi",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".webm",
}


def discover_video_files(source: Path) -> list[Path]:
    source = source.expanduser().resolve()

    if not source.exists():
        raise FileNotFoundError(f"Video source does not exist: {source}")

    if source.is_file():
        if source.suffix.lower() not in VIDEO_EXTENSIONS:
            raise ValueError(f"Unsupported video file: {source}")
        return [source]

    videos = sorted(
        file_path
        for file_path in source.rglob("*")
        if file_path.is_file() and file_path.suffix.lower() in VIDEO_EXTENSIONS
    )

    if not videos:
        raise FileNotFoundError(f"No supported video files found in: {source}")

    return videos


def discover_video_files_from_sources(sources: list[Path]) -> list[Path]:
    videos: list[Path] = []
    seen: set[Path] = set()

    for source in sources:
        for video_path in discover_video_files(source):
            if video_path in seen:
                continue
            seen.add(video_path)
            videos.append(video_path)

    if not videos:
        raise FileNotFoundError("No supported video files were found in the configured sources.")

    return sorted(videos)
