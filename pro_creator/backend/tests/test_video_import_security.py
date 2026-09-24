import socket

import pytest
from fastapi import HTTPException

import app.routers.video as video_router


def test_remote_video_url_rejects_non_http_scheme() -> None:
    with pytest.raises(HTTPException) as exc:
        video_router._validate_public_remote_url("file:///etc/passwd")
    assert exc.value.status_code == 400


def test_remote_video_url_rejects_localhost() -> None:
    with pytest.raises(HTTPException) as exc:
        video_router._validate_public_remote_url("http://localhost/video.mp4")
    assert exc.value.status_code == 400


def test_remote_video_url_rejects_private_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 80))],
    )
    with pytest.raises(HTTPException) as exc:
        video_router._validate_public_remote_url("http://private.example/video.mp4")
    assert exc.value.status_code == 400


def test_remote_video_url_accepts_public_ip(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))],
    )
    video_router._validate_public_remote_url("https://media.example/video.mp4")


def test_remote_video_url_redacts_query_secret() -> None:
    assert video_router._redact_remote_url("https://media.example/video.mp4?token=secret#x") == "https://media.example/video.mp4"
