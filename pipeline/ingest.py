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


def is_supported_video_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS


def discover_video_files(source: Path) -> list[Path]:
    source = source.expanduser().resolve()

    if not source.exists():
        raise FileNotFoundError(f"Video source does not exist: {source}")

    if source.is_file():
        if not is_supported_video_file(source):
            raise ValueError(f"Unsupported video file: {source}")
        return [source]

    videos = _discover_video_files_in_directory(source)

    if not videos:
        raise FileNotFoundError(f"No supported video files found in: {source}")

    return videos


def discover_optional_video_files(source: Path) -> list[Path]:
    source = source.expanduser().resolve()

    if not source.exists():
        return []

    if source.is_file():
        return [source] if is_supported_video_file(source) else []

    return _discover_video_files_in_directory(source)


def discover_video_files_from_sources(sources: list[Path]) -> list[Path]:
    videos = merge_unique_video_paths(*(discover_video_files(source) for source in sources))

    if not videos:
        raise FileNotFoundError("No supported video files were found in the configured sources.")

    return videos


def discover_optional_video_files_from_sources(sources: list[Path]) -> list[Path]:
    return merge_unique_video_paths(*(discover_optional_video_files(source) for source in sources))


def merge_unique_video_paths(*groups: list[Path]) -> list[Path]:
    videos: list[Path] = []
    seen: set[Path] = set()

    for group in groups:
        for video_path in group:
            resolved_path = video_path.expanduser().resolve()
            if resolved_path in seen:
                continue
            seen.add(resolved_path)
            videos.append(resolved_path)

    return videos


def _discover_video_files_in_directory(source: Path) -> list[Path]:
    return sorted(
        file_path
        for file_path in source.rglob("*")
        if is_supported_video_file(file_path)
    )
