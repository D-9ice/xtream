from pathlib import Path

import app.routers.video as video_router


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {
            "text": "Hello world. Second sentence",
            "language": "en",
            "duration": 3.2,
            "words": [
                {"text": "Hello", "start": 0.0, "end": 0.5},
                {"text": "world.", "start": 0.5, "end": 1.0},
                {"text": "Second", "start": 1.4, "end": 2.0},
                {"text": "sentence", "start": 2.0, "end": 3.2},
            ],
        }


def test_xai_stt_groups_words_into_timed_segments(monkeypatch, tmp_path: Path) -> None:
    audio = tmp_path / "sample.mp3"
    audio.write_bytes(b"audio")
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["data"] = kwargs["data"]
        captured["files"] = kwargs["files"]
        return _FakeResponse()

    monkeypatch.setattr(video_router, "XAI_API_KEY", "test-key")
    monkeypatch.setattr(video_router, "XAI_BASE_URL", "https://api.x.ai/v1")
    monkeypatch.setattr(video_router, "XAI_STT_MODEL", "grok-voice-transcribe-2.0")
    monkeypatch.setattr(video_router.requests, "post", fake_post)

    segments, metadata = video_router._transcribe_with_xai(audio)

    assert captured["url"] == "https://api.x.ai/v1/stt"
    assert ("model", "grok-voice-transcribe-2.0") in captured["data"]
    assert segments == [
        {"segment_id": 1, "start": 0.0, "end": 1.0, "text": "Hello world."},
        {"segment_id": 2, "start": 1.4, "end": 3.2, "text": "Second sentence"},
    ]
    assert metadata["provider"] == "xai"
    assert metadata["language"] == "en"


def test_xai_stt_falls_back_to_full_text_when_words_are_absent() -> None:
    assert video_router._segments_from_xai_words([], "Complete transcript", 4.2) == [
        {"segment_id": 1, "start": 0.0, "end": 4.2, "text": "Complete transcript"}
    ]
