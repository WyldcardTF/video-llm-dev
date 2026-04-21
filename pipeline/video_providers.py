from __future__ import annotations

import base64
import hashlib
import hmac
import json
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
    provider_options: dict[str, Any] = field(default_factory=dict)


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


class KlingVideoProvider(VideoProvider):
    provider_name = "kling"

    def generate(self, request: VideoGenerationRequest) -> VideoGenerationResult:
        if not request.settings.kling_api_access_key or not request.settings.kling_api_secret_key:
            raise RuntimeError(
                "KLING_API_ACCESS_KEY and KLING_API_SECRET_KEY must be set in .env "
                "to use Kling video generation."
            )

        base_url = request.settings.kling_base_url.rstrip("/")
        headers = _kling_headers(request.settings)
        endpoint, payload, used_references = _build_kling_payload(request)
        if request.negative_prompt:
            payload["negative_prompt"] = request.negative_prompt

        response = requests.post(f"{base_url}{endpoint}", headers=headers, json=payload, timeout=60)
        _raise_for_provider_response(response, "Kling generation request failed")
        response_payload = response.json()
        task_id = _first_value(response_payload, "task_id", "id", "generation_id")
        if not task_id:
            data = response_payload.get("data")
            if isinstance(data, dict):
                task_id = _first_value(data, "task_id", "id", "generation_id")
        if not task_id:
            raise RuntimeError(f"Kling did not return a task id: {response.text}")

        poll_interval = max(request.run_parameters.generation.video_poll_interval_ms / 1000.0, 1.0)
        poll_endpoint = _format_kling_status_endpoint(
            request.settings.kling_status_endpoint_template,
            endpoint,
            str(task_id),
        )
        while True:
            poll_response = requests.get(f"{base_url}{poll_endpoint}", headers=headers, timeout=60)
            _raise_for_provider_response(poll_response, "Kling polling failed")
            payload = poll_response.json()
            status = _kling_status(payload)
            if status in {"failed", "error", "rejected"}:
                raise RuntimeError(f"Kling generation failed: {payload}")
            video_url = _find_video_url(payload)
            if status in {"completed", "complete", "succeeded", "success", "done"} and video_url:
                _download_http_file(video_url, request.output_path)
                return VideoGenerationResult(
                    asset_path=request.output_path,
                    remote_id=str(task_id),
                    used_reference_paths=used_references,
                )
            if video_url and not status:
                _download_http_file(video_url, request.output_path)
                return VideoGenerationResult(
                    asset_path=request.output_path,
                    remote_id=str(task_id),
                    used_reference_paths=used_references,
                )
            time.sleep(poll_interval)


def get_video_provider(provider_name: str) -> VideoProvider:
    if provider_name in {"auto", "kling"}:
        return KlingVideoProvider()
    raise ValueError("Only the Kling video generation backend is supported.")


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


def _build_kling_payload(request: VideoGenerationRequest) -> tuple[str, dict[str, Any], list[str]]:
    generation = request.run_parameters.generation
    mode = generation.kling_generation_mode.strip().lower()
    image_references = [
        reference
        for reference in request.references
        if reference.media_kind == "image" and _kling_reference_value(reference, generation.kling_local_image_transport)
    ]
    min_images = max(generation.kling_multi_image_min_images, 2)
    max_images = min(max(generation.kling_multi_image_max_images, min_images), 4)

    if mode in {"multi_image_to_video", "multi-image-to-video", "multi_image2video", "multi-image2video"}:
        if len(image_references) < min_images:
            raise RuntimeError(
                "Kling multi-image-to-video needs at least "
                f"{min_images} image references for each shot. "
                "Add scene reference_assets images, lower kling_multi_image_min_images, "
                "or set generation.kling_generation_mode to image_to_video/text_to_video."
            )
        selected = image_references[:max_images]
        payload = _kling_common_payload(request)
        payload[generation.kling_model_field or "model_name"] = _kling_model_name_for_endpoint(
            request,
            request.settings.kling_multi_image_endpoint,
        )
        payload["image_list"] = [
            {"image": _kling_reference_value(reference, generation.kling_local_image_transport)}
            for reference in selected
        ]
        return request.settings.kling_multi_image_endpoint, payload, [reference.path for reference in selected]

    image_url_references = [reference for reference in image_references if reference.url]
    if mode in {"image_to_video", "image2video"} or image_url_references:
        endpoint = request.settings.kling_image_endpoint
        payload = _kling_common_payload(request)
        payload[generation.kling_model_field or "model_name"] = _kling_model_name_for_endpoint(request, endpoint)
        first_reference = image_url_references[:1]
        if first_reference:
            payload["image"] = image_url_references[0].url
            _add_kling_camera_control(payload, request)
            return endpoint, payload, [reference.path for reference in first_reference]

        first_local_reference = _first_local_reference(request.references, media_kind="image")
        if first_local_reference is not None:
            payload["image"] = _kling_reference_value(
                first_local_reference,
                generation.kling_local_image_transport,
            )
            _add_kling_camera_control(payload, request)
            return endpoint, payload, [first_local_reference.path]
        return endpoint, payload, []

    endpoint = request.settings.kling_text_endpoint
    payload = _kling_common_payload(request)
    payload[generation.kling_model_field or "model_name"] = _kling_model_name_for_endpoint(request, endpoint)
    _add_kling_camera_control(payload, request)
    return endpoint, payload, []


def _kling_common_payload(request: VideoGenerationRequest) -> dict[str, Any]:
    generation = request.run_parameters.generation
    payload: dict[str, Any] = {
        "prompt": request.prompt[:2500],
        "duration": str(request.duration_seconds),
        "aspect_ratio": request.aspect_ratio or "9:16",
        "mode": _normalize_kling_mode(generation.kling_mode or request.model_selection.kling_mode),
        "sound": "on" if (generation.kling_sound or request.model_selection.kling_sound) else "off",
    }
    if request.resolution:
        payload["resolution"] = request.resolution
    if generation.seed is not None:
        payload["seed"] = generation.seed
    if generation.kling_cfg_scale is not None:
        payload["cfg_scale"] = generation.kling_cfg_scale
    if generation.kling_callback_url:
        payload["callback_url"] = generation.kling_callback_url
    if generation.kling_external_task_id:
        payload["external_task_id"] = generation.kling_external_task_id
    payload.update(generation.kling_extra_payload)

    provider_kling_options = request.provider_options.get("kling")
    if isinstance(provider_kling_options, dict):
        payload.update(
            {
                key: value
                for key, value in provider_kling_options.items()
                if key != "camera_control"
            }
        )
    return payload


def _add_kling_camera_control(payload: dict[str, Any], request: VideoGenerationRequest) -> None:
    camera_control = request.run_parameters.generation.kling_camera_control
    provider_kling_options = request.provider_options.get("kling")
    if isinstance(provider_kling_options, dict) and isinstance(provider_kling_options.get("camera_control"), dict):
        camera_control = provider_kling_options["camera_control"]
    if camera_control:
        payload["camera_control"] = camera_control


def _kling_model_name_for_endpoint(request: VideoGenerationRequest, endpoint: str) -> str:
    model_name = request.model_selection.model
    if endpoint == request.settings.kling_multi_image_endpoint:
        # The current official multi-image endpoint documents kling-v1-6.
        return "kling-v1-6"
    return model_name


def _kling_headers(settings: Settings) -> dict[str, str]:
    token = _kling_bearer_token(
        settings.kling_api_access_key or "",
        settings.kling_api_secret_key or "",
    )
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _kling_bearer_token(access_key: str, secret_key: str) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "iss": access_key,
        "exp": now + 1800,
        "nbf": now - 5,
    }
    signing_input = ".".join((_jwt_b64url(header), _jwt_b64url(payload)))
    signature = hmac.new(
        secret_key.encode("utf-8"),
        signing_input.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode('ascii')}"


def _jwt_b64url(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode("ascii")


def _normalize_kling_mode(mode: str | None) -> str:
    lowered = (mode or "").strip().lower()
    if lowered in {"", "standard", "std"}:
        return "std"
    if lowered in {"professional", "pro"}:
        return "pro"
    return lowered


def _kling_reference_value(reference: PreparedReference, transport: str) -> str | None:
    if reference.url:
        return reference.url
    if transport.strip().lower() != "base64":
        return None
    path = Path(reference.path)
    if not path.exists():
        return None
    return _base64_file(path)


def _format_kling_status_endpoint(template: str, endpoint: str, task_id: str) -> str:
    if not template:
        template = "{endpoint}/{task_id}"
    endpoint = endpoint.rstrip("/")
    formatted = template.format(endpoint=endpoint, task_id=task_id)
    if not formatted.startswith("/"):
        formatted = "/" + formatted
    return formatted


def _kling_status(payload: dict[str, Any]) -> str:
    status = str(_first_value(payload, "status", "state", "task_status") or "").lower()
    data = payload.get("data")
    if not status and isinstance(data, dict):
        status = str(_first_value(data, "status", "state", "task_status") or "").lower()
    if status == "succeed":
        return "success"
    if status == "submitted":
        return "processing"
    return status


def _base64_file(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


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
