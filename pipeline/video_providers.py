from __future__ import annotations

import base64
import mimetypes
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests

from .config import Settings
from .run_config import RunParameters
from .video_models import VideoModelSelection


@dataclass(frozen=True)
class PreparedReference:
    path: str
    role: str
    label: str
    prompt_hint: str
    provider_use: str
    media_kind: str | None
    url: str | None = None
    mime_type: str | None = None


@dataclass(frozen=True)
class VideoGenerationRequest:
    prompt: str
    negative_prompt: str
    output_path: Path
    model_selection: VideoModelSelection
    run_parameters: RunParameters
    settings: Settings
    duration_seconds: int
    size: str | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    references: list[PreparedReference] = field(default_factory=list)


@dataclass(frozen=True)
class VideoGenerationResult:
    asset_path: Path
    remote_id: str | None = None
    revised_prompt: str | None = None
    used_reference_paths: list[str] = field(default_factory=list)


class VideoProvider:
    provider_name = "base"

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        raise NotImplementedError


class OpenAIVideoProvider(VideoProvider):
    provider_name = "openai_video"

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        if not request.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY must be set in .env to use OpenAI/Sora video generation.")

        from openai import OpenAI

        client = OpenAI(api_key=request.settings.openai_api_key)
        request_kwargs: dict[str, Any] = {
            "model": request.model_selection.model,
            "prompt": _combine_prompt(request.prompt, request.negative_prompt),
            "seconds": request.duration_seconds,
            "size": request.size,
            "poll_interval_ms": request.run_parameters.generation.video_poll_interval_ms,
        }
        request_kwargs = {key: value for key, value in request_kwargs.items() if value is not None}

        input_reference = _first_local_reference(request.references, media_kind="image")
        used_references: list[str] = []
        if input_reference is not None:
            request_kwargs["input_reference"] = Path(input_reference.path)
            used_references.append(input_reference.path)

        video = client.videos.create_and_poll(**request_kwargs)
        status = getattr(video, "status", None)
        if status != "completed":
            error = getattr(video, "error", None)
            raise RuntimeError(f"OpenAI video generation failed with status={status} error={error}")

        content = client.videos.download_content(video.id, variant="video")
        request.output_path.write_bytes(content.content)
        return VideoGenerationResult(
            asset_path=request.output_path,
            remote_id=getattr(video, "id", None),
            revised_prompt=getattr(video, "revised_prompt", None),
            used_reference_paths=used_references,
        )


class GoogleVeoProvider(VideoProvider):
    provider_name = "google_veo"

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        project = request.settings.google_vertex_project
        if not project:
            raise RuntimeError("GOOGLE_VERTEX_PROJECT must be set in .env to use Google Veo.")

        location = request.settings.google_vertex_location
        model = request.model_selection.model
        token = _google_access_token(request.settings)
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }
        base_url = (
            f"https://{location}-aiplatform.googleapis.com/v1/projects/{project}"
            f"/locations/{location}/publishers/google/models/{model}"
        )

        instance: dict[str, Any] = {"prompt": request.prompt}
        reference_images = _google_reference_images(request)
        used_references = [reference.path for reference in reference_images]
        if reference_images:
            instance["referenceImages"] = [
                {
                    "image": {
                        "bytesBase64Encoded": _base64_file(Path(reference.path)),
                        "mimeType": reference.mime_type or _mime_type(Path(reference.path)),
                    },
                    "referenceType": "asset",
                }
                for reference in reference_images
            ]

        parameters: dict[str, Any] = {
            "durationSeconds": request.duration_seconds,
            "sampleCount": request.run_parameters.generation.google_sample_count,
        }
        if request.aspect_ratio:
            parameters["aspectRatio"] = request.aspect_ratio
        if request.resolution:
            parameters["resolution"] = request.resolution
        if request.negative_prompt:
            parameters["negativePrompt"] = request.negative_prompt
        if request.run_parameters.generation.google_person_generation:
            parameters["personGeneration"] = request.run_parameters.generation.google_person_generation
        if request.run_parameters.generation.google_output_gcs_uri:
            parameters["storageUri"] = request.run_parameters.generation.google_output_gcs_uri
        if request.run_parameters.generation.seed is not None:
            parameters["seed"] = request.run_parameters.generation.seed

        response = requests.post(
            f"{base_url}:predictLongRunning",
            headers=headers,
            json={"instances": [instance], "parameters": parameters},
            timeout=60,
        )
        _raise_for_provider_response(response, "Google Veo request failed")
        operation_name = response.json().get("name")
        if not operation_name:
            raise RuntimeError(f"Google Veo did not return an operation name: {response.text}")

        poll_url = f"{base_url}:fetchPredictOperation"
        poll_interval = max(request.run_parameters.generation.video_poll_interval_ms / 1000.0, 1.0)
        while True:
            poll_response = requests.post(
                poll_url,
                headers=headers,
                json={"operationName": operation_name},
                timeout=60,
            )
            _raise_for_provider_response(poll_response, "Google Veo polling failed")
            payload = poll_response.json()
            if payload.get("error"):
                raise RuntimeError(f"Google Veo generation failed: {payload['error']}")
            if payload.get("done"):
                _write_google_video_payload(payload, request.output_path)
                return VideoGenerationResult(
                    asset_path=request.output_path,
                    remote_id=operation_name,
                    used_reference_paths=used_references,
                )
            time.sleep(poll_interval)


class KlingVideoProvider(VideoProvider):
    provider_name = "kling"

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        if not request.settings.kling_api_key:
            raise RuntimeError("KLING_API_KEY must be set in .env to use Kling video generation.")

        base_url = request.settings.kling_base_url.rstrip("/")
        headers = {
            "Authorization": f"Bearer {request.settings.kling_api_key}",
            "Content-Type": "application/json",
        }
        image_urls = [reference.url for reference in request.references if reference.url and reference.media_kind == "image"]
        endpoint = "/v1/videos/image2video" if image_urls else "/v1/videos/text2video"
        payload: dict[str, Any] = {
            "model": request.model_selection.model,
            "prompt": request.prompt,
            "duration": request.duration_seconds,
            "aspect_ratio": request.aspect_ratio or "9:16",
            "mode": request.run_parameters.generation.kling_mode
            or request.model_selection.kling_mode
            or "standard",
        }
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt
        if request.run_parameters.generation.kling_sound or request.model_selection.kling_sound:
            payload["sound"] = True
        if image_urls:
            payload["image_urls"] = image_urls[:1]

        response = requests.post(f"{base_url}{endpoint}", headers=headers, json=payload, timeout=60)
        _raise_for_provider_response(response, "Kling generation request failed")
        response_payload = response.json()
        task_id = _first_value(response_payload, "task_id", "id")
        if not task_id:
            data = response_payload.get("data")
            if isinstance(data, dict):
                task_id = _first_value(data, "task_id", "id")
        if not task_id:
            raise RuntimeError(f"Kling did not return a task id: {response.text}")

        poll_interval = max(request.run_parameters.generation.video_poll_interval_ms / 1000.0, 1.0)
        while True:
            poll_response = requests.get(f"{base_url}/v1/videos/{task_id}", headers=headers, timeout=60)
            _raise_for_provider_response(poll_response, "Kling polling failed")
            payload = poll_response.json()
            status = str(_first_value(payload, "status", "state") or "").lower()
            if status in {"failed", "error", "rejected"}:
                raise RuntimeError(f"Kling generation failed: {payload}")
            video_url = _find_video_url(payload)
            if status in {"completed", "complete", "succeeded", "success", "done"} and video_url:
                _download_http_file(video_url, request.output_path)
                return VideoGenerationResult(
                    asset_path=request.output_path,
                    remote_id=str(task_id),
                    used_reference_paths=image_urls[:1],
                )
            if video_url and not status:
                _download_http_file(video_url, request.output_path)
                return VideoGenerationResult(
                    asset_path=request.output_path,
                    remote_id=str(task_id),
                    used_reference_paths=image_urls[:1],
                )
            time.sleep(poll_interval)


def get_video_provider(provider_name: str) -> VideoProvider:
    if provider_name == "openai_video":
        return OpenAIVideoProvider()
    if provider_name == "google_veo":
        return GoogleVeoProvider()
    if provider_name == "kling":
        return KlingVideoProvider()
    raise ValueError(
        f"Unsupported video generation provider '{provider_name}'. "
        "Use one of: auto, openai_video, google_veo, kling."
    )


def _combine_prompt(prompt: str, negative_prompt: str) -> str:
    if not negative_prompt:
        return prompt
    return f"{prompt} Avoid: {negative_prompt}"


def _first_local_reference(
    references: list[PreparedReference],
    media_kind: str,
) -> PreparedReference | None:
    for reference in references:
        if reference.media_kind != media_kind:
            continue
        if reference.url:
            continue
        if Path(reference.path).exists():
            return reference
    return None


def _google_reference_images(request: VideoGenerationRequest) -> list[PreparedReference]:
    model = request.model_selection.model
    if "lite" in model:
        return []
    limit = max(request.run_parameters.generation.reference_asset_limit, request.model_selection.reference_asset_limit)
    references: list[PreparedReference] = []
    for reference in request.references:
        if len(references) >= limit:
            break
        if reference.media_kind != "image" or reference.url:
            continue
        if reference.role == "style":
            continue
        if not Path(reference.path).exists():
            continue
        references.append(reference)
    return references


def _google_access_token(settings: Settings) -> str:
    if settings.google_vertex_access_token:
        return settings.google_vertex_access_token

    try:
        import google.auth
        from google.auth.transport.requests import Request

        credentials, _project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        credentials.refresh(Request())
        if credentials.token:
            return credentials.token
    except Exception:
        pass

    process = subprocess.run(
        ["gcloud", "auth", "print-access-token"],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode == 0 and process.stdout.strip():
        return process.stdout.strip()
    raise RuntimeError(
        "Could not obtain a Google Vertex access token. Set GOOGLE_VERTEX_ACCESS_TOKEN, "
        "configure Application Default Credentials, or run `gcloud auth login`."
    )


def _base64_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _mime_type(path: Path) -> str:
    mime_type, _encoding = mimetypes.guess_type(str(path))
    return mime_type or "application/octet-stream"


def _write_google_video_payload(payload: dict[str, Any], output_path: Path) -> None:
    videos = _extract_google_videos(payload)
    if not videos:
        raise RuntimeError(f"Google Veo completed without returning video output: {payload}")

    first_video = videos[0]
    encoded = first_video.get("bytesBase64Encoded") or first_video.get("bytes_base64_encoded")
    if encoded:
        output_path.write_bytes(base64.b64decode(encoded))
        return

    gcs_uri = first_video.get("gcsUri") or first_video.get("uri")
    if gcs_uri and str(gcs_uri).startswith("gs://"):
        _download_gcs_file(str(gcs_uri), output_path)
        return

    http_url = first_video.get("url") or first_video.get("downloadUrl")
    if http_url:
        _download_http_file(str(http_url), output_path)
        return

    raise RuntimeError(f"Google Veo returned an unsupported video payload: {first_video}")


def _extract_google_videos(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response", payload)
    if isinstance(response, dict):
        videos = response.get("videos")
        if isinstance(videos, list):
            return [item for item in videos if isinstance(item, dict)]
        samples = response.get("generatedSamples")
        if isinstance(samples, list):
            found: list[dict[str, Any]] = []
            for sample in samples:
                if isinstance(sample, dict) and isinstance(sample.get("video"), dict):
                    found.append(sample["video"])
            return found
    return []


def _download_gcs_file(gcs_uri: str, output_path: Path) -> None:
    process = subprocess.run(
        ["gcloud", "storage", "cp", gcs_uri, str(output_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0 or not output_path.exists():
        raise RuntimeError(
            "Google Veo returned a Cloud Storage URI, but `gcloud storage cp` could not download it. "
            f"URI: {gcs_uri}. stderr: {process.stderr.strip()}"
        )


def _download_http_file(url: str, output_path: Path) -> None:
    response = requests.get(url, timeout=120)
    _raise_for_provider_response(response, f"Could not download generated video from {url}")
    output_path.write_bytes(response.content)


def _raise_for_provider_response(response: requests.Response, message: str) -> None:
    if response.ok:
        return
    raise RuntimeError(f"{message}: HTTP {response.status_code} {response.text}")


def _first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _find_video_url(payload: Any) -> str | None:
    if isinstance(payload, dict):
        for key, value in payload.items():
            lowered = str(key).lower()
            if lowered in {"video_url", "videourl", "url", "download_url", "downloadurl"}:
                if isinstance(value, str) and value.startswith("http"):
                    return value
            found = _find_video_url(value)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _find_video_url(item)
            if found:
                return found
    return None
