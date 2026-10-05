#!/usr/bin/env python3
"""ml/fetch_model.py  --  download the trained model so a fresh clone can serve"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "model_artifacts"

REPO = "abhinavtop1G/BARRIER-X_SIH26165"
TAG = "model-v1"
ASSET = "avertx-sif-model-v1.tar.gz"
URL = f"https://github.com/{REPO}/releases/download/{TAG}/{ASSET}"
SHA256 = "c2aa0a2a3d386f188dad3cbfd08d8a71b4726a3846845ca0c58f7de4ecc8e56a"
SIZE_MB = 531


def servable() -> Path | None:
    """The promoted checkpoint, if a usable one is already on disk."""
    sys.path.insert(0, str(ROOT))
    from ml.artifacts import read_serving

    served = read_serving()
    if served:
        onnx = Path(served["onnx_dir"]) if served.get("onnx_dir") else None
        if onnx and any(onnx.glob("*.onnx")):
            return Path(served["checkpoint"])
    return None


def _via_urllib(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url) as r, dest.open("wb") as fh:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        while chunk := r.read(1 << 20):
            fh.write(chunk)
            done += len(chunk)
            if total:
                pct = 100 * done / total
                print(f"\r  [{'#' * int(pct / 2.5):<40}] {pct:5.1f}%  "
                      f"{done/1e6:6.0f}/{total/1e6:.0f} MB", end="", flush=True)
    print()


def _via_gh(url: str, dest: Path) -> None:
    subprocess.run(
        ["gh", "release", "download", TAG, "--repo", REPO,
         "--pattern", ASSET, "--output", str(dest), "--clobber"],
        check=True,
    )


def _via_curl(url: str, dest: Path) -> None:
    progress = ["--progress-bar"] if sys.stdout.isatty() else ["-sS"]
    subprocess.run(["curl", "-fL", *progress, "-o", str(dest), url], check=True)


def download(url: str, dest: Path) -> None:
    """Try each transport in turn."""
    print(f"[fetch] {url}")
    print(f"[fetch] ~{SIZE_MB} MB, this takes a minute or two")

    strategies = [("gh", _via_gh), ("curl", _via_curl), ("python urllib", _via_urllib)]
    errors = []
    for name, fn in strategies:
        if name != "python urllib" and shutil.which(name.split()[0]) is None:
            continue
        try:
            print(f"[fetch] trying {name}")
            fn(url, dest)
            if dest.exists() and dest.stat().st_size > 1_000_000:
                return
            errors.append(f"  {name}: produced no usable file")
        except Exception as exc:
            errors.append(f"  {name}: {type(exc).__name__}: {str(exc)[:120]}")
            dest.unlink(missing_ok=True)
    raise RuntimeError("every download strategy failed:\n" + "\n".join(errors))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Refuse absolute paths and parent traversal."""
    dest = dest.resolve()
    for m in tar.getmembers():
        target = (dest / m.name).resolve()
        if not str(target).startswith(str(dest)):
            raise SystemExit(f"Refusing unsafe path in archive: {m.name}")
        if m.issym() or m.islnk():
            raise SystemExit(f"Refusing link in archive: {m.name}")
    tar.extractall(dest)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=URL)
    ap.add_argument("--force", action="store_true", help="re-download over an existing model")
    ap.add_argument("--check", action="store_true", help="report status and exit")
    ap.add_argument("--no-verify", action="store_true", help="skip the SHA256 check")
    args = ap.parse_args()

    have = servable()
    if args.check:
        if have:
            print(f"[ OK ] servable model present: {have}")
            return 0
        print("[FAIL] no servable model. Run: python -m ml.fetch_model")
        return 1

    if have and not args.force:
        print(f"[skip] a servable model is already present: {have}")
        print("       pass --force to re-download")
        return 0

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / ASSET
        try:
            download(args.url, archive)
        except Exception as exc:
            print(f"\n[FAIL] download failed: {type(exc).__name__}: {exc}")
            print(f"       fetch it manually from https://github.com/{REPO}/releases/tag/{TAG}")
            print(f"       then: tar -xzf {ASSET} -C {ROOT}")
            return 1

        if not args.no_verify:
            got = sha256(archive)
            if got != SHA256:
                print(f"[FAIL] checksum mismatch\n  expected {SHA256}\n  got      {got}")
                return 1
            print(f"[ OK ] sha256 {got[:16]}...")

        print(f"[extract] -> {ART}")
        with tarfile.open(archive, "r:gz") as tar:
            safe_extract(tar, ROOT)

    ck = servable()
    if not ck:
        print("[FAIL] extracted, but no servable model found afterwards")
        return 1
    print(f"[ OK ] model ready: {ck}")
    print("\nNext:")
    print("  python -m ml.selftest                       # 16 checks, end to end")
    print("  uvicorn api.main:app --port 8000            # serve")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
