#!/usr/bin/env python3
"""Validate ElevenLabs credentials by generating a short test clip."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing {name}. Set it in your environment before running.")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a test clip via ElevenLabs TTS.")
    parser.add_argument(
        "--text",
        default="Hello from Pro Creator. This is a quick ElevenLabs connectivity check.",
        help="Text to synthesize.",
    )
    parser.add_argument(
        "--output",
        default="elevenlabs_test.mp3",
        help="Output audio filename.",
    )
    args = parser.parse_args()

    try:
        api_key = _require_env("ELEVENLABS_API_KEY")
        voice_id = _require_env("ELEVENLABS_VOICE_ID")
    except RuntimeError as exc:
        print(str(exc))
        return 1

    model_id = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": api_key, "Accept": "audio/mpeg"}
    payload = {"text": args.text, "model_id": model_id}

    response = requests.post(url, json=payload, headers=headers, timeout=30)
    if response.status_code != 200:
        print(f"ElevenLabs request failed ({response.status_code}): {response.text}")
        return 1

    output_path = Path(args.output)
    output_path.write_bytes(response.content)
    print(f"Saved test audio to {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
