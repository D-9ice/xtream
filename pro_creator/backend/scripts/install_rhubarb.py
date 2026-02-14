#!/usr/bin/env python3
"""Download and verify Rhubarb Lip Sync binary."""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import sys
import tarfile
import urllib.request
import zipfile
from pathlib import Path

DEFAULT_VERSION = "1.13.0"
DEFAULT_URLS = {
    "Darwin": f"https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v{DEFAULT_VERSION}/Rhubarb-Lip-Sync-{DEFAULT_VERSION}-macOS.zip",
    "Linux": f"https://github.com/DanielSWolf/rhubarb-lip-sync/releases/download/v{DEFAULT_VERSION}/Rhubarb-Lip-Sync-{DEFAULT_VERSION}-Linux.zip",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response, destination.open("wb") as out:
        shutil.copyfileobj(response, out)


def _extract(archive_path: Path, destination: Path) -> None:
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(destination)
    elif archive_path.suffixes[-2:] == [".tar", ".gz"]:
        with tarfile.open(archive_path) as archive:
            archive.extractall(destination)
    else:
        raise RuntimeError(f"Unsupported archive type: {archive_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and verify Rhubarb Lip Sync.")
    parser.add_argument("--version", default=DEFAULT_VERSION, help="Rhubarb version tag.")
    parser.add_argument("--url", default=None, help="Override download URL.")
    parser.add_argument("--sha256", default=None, help="Expected SHA256 checksum.")
    parser.add_argument("--install-dir", default="./tools/rhubarb", help="Destination folder.")
    args = parser.parse_args()

    system = platform.system()
    url = args.url or DEFAULT_URLS.get(system)
    if not url:
        print(f"Unsupported platform {system}. Provide --url explicitly.")
        return 1

    if not args.sha256:
        print("A SHA256 checksum is required for verification. Provide --sha256.")
        return 1

    install_dir = Path(args.install_dir).resolve()
    archive_path = install_dir / "rhubarb_download"
    print(f"Downloading Rhubarb from {url}...")
    _download(url, archive_path)

    checksum = _sha256(archive_path)
    if checksum != args.sha256:
        print("Checksum mismatch.")
        print(f"Expected: {args.sha256}")
        print(f"Actual:   {checksum}")
        return 1

    _extract(archive_path, install_dir)
    archive_path.unlink(missing_ok=True)

    # Try to locate the rhubarb binary
    rhubarb_candidates = list(install_dir.rglob("rhubarb"))
    if not rhubarb_candidates:
        print("Rhubarb binary not found after extraction.")
        return 1

    rhubarb_path = rhubarb_candidates[0]
    rhubarb_path.chmod(rhubarb_path.stat().st_mode | 0o111)
    print(f"Rhubarb installed at {rhubarb_path}")
    print("Set RHUBARB_PATH to this location or add it to your PATH.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
