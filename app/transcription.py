"""经用户明确同意的音频转写适配器，统一容量、超时和安全错误处理。"""

from pathlib import Path
from typing import Protocol

import httpx

from app.config import Settings


class TranscriptionUnavailable(RuntimeError):
    pass


class TranscriptionProvider(Protocol):
    def transcribe(
        self,
        *,
        path: Path,
        content_type: str,
        filename: str,
    ) -> list[dict[str, object]]: ...


class HttpTranscriptionProvider:
    """Adapter for a configured multipart transcription endpoint."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def transcribe(
        self,
        *,
        path: Path,
        content_type: str,
        filename: str,
    ) -> list[dict[str, object]]:
        if (
            not self.settings.transcription_enabled
            or not self.settings.transcription_api_url
            or not self.settings.transcription_api_key
        ):
            raise TranscriptionUnavailable("音频转写服务尚未配置")
        with path.open("rb") as source:
            response = httpx.post(
                self.settings.transcription_api_url,
                headers={
                    "Authorization": (
                        f"Bearer {self.settings.transcription_api_key}"
                    )
                },
                files={"file": (filename, source, content_type)},
                data={"response_format": "verbose_json"},
                timeout=self.settings.transcription_timeout_seconds,
            )
        response.raise_for_status()
        payload = response.json()
        raw_segments = payload.get("segments")
        if not isinstance(raw_segments, list):
            text = str(payload.get("text") or "").strip()
            raw_segments = [{"text": text}] if text else []
        segments = []
        for index, item in enumerate(raw_segments):
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            segments.append(
                {
                    "segment_id": f"segment-{index + 1}",
                    "speaker": "unknown",
                    "text": text,
                    "start_seconds": item.get("start"),
                    "end_seconds": item.get("end"),
                }
            )
        if not segments:
            raise ValueError("转写服务未返回可用文本")
        return segments
