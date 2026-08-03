"""外部转写提供方适配器的测试。"""

from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.transcription import (
    HttpTranscriptionProvider,
    TranscriptionUnavailable,
)


def settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        transcription_enabled=True,
        transcription_api_url="https://transcription.invalid/v1/audio",
        transcription_api_key="secret",
        **overrides,
    )


def test_http_transcription_maps_provider_speakers_to_unknown(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio = tmp_path / "synthetic.wav"
    audio.write_bytes(b"RIFF....WAVE")
    captured = {}

    def post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return httpx.Response(
            200,
            json={
                "segments": [
                    {
                        "speaker": "speaker_0",
                        "text": "请介绍项目",
                        "start": 0,
                        "end": 1,
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    segments = HttpTranscriptionProvider(settings()).transcribe(
        path=audio,
        content_type="audio/wav",
        filename="synthetic.wav",
    )

    assert segments[0]["speaker"] == "unknown"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["timeout"] == 120


def test_http_transcription_requires_complete_configuration(
    tmp_path: Path,
) -> None:
    audio = tmp_path / "synthetic.wav"
    audio.write_bytes(b"RIFF....WAVE")
    provider = HttpTranscriptionProvider(
        Settings(_env_file=None, transcription_enabled=False)
    )

    with pytest.raises(TranscriptionUnavailable):
        provider.transcribe(
            path=audio,
            content_type="audio/wav",
            filename="synthetic.wav",
        )


def test_http_transcription_rejects_empty_provider_response(
    tmp_path: Path,
    monkeypatch,
) -> None:
    audio = tmp_path / "synthetic.wav"
    audio.write_bytes(b"RIFF....WAVE")
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **_: httpx.Response(
            200,
            json={"segments": []},
            request=httpx.Request("POST", url),
        ),
    )

    with pytest.raises(ValueError, match="可用文本"):
        HttpTranscriptionProvider(settings()).transcribe(
            path=audio,
            content_type="audio/wav",
            filename="synthetic.wav",
        )
