"""Download pinned public runtime assets into this project. Never called by app startup.

Run with Python 3.12. For restricted networks optionally set HTTPS_PROXY before use.
This installer downloads files only; Python package installation is documented separately.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
QWEN_REV = "bc640142c66e1fdd12af0bd68f40445458f3869b"
BGE_REV = "7999e1d3359715c523056ef9478215996d62a620"
LLAMA_TAG = "b10950"


def hf(repo, rev, name):
    return f"https://huggingface.co/{repo}/resolve/{rev}/{name}"


ASSETS = [
    {
        "path": "runtime/downloads/llama-b10950-bin-win-vulkan-x64.zip",
        "url": "https://github.com/ggml-org/llama.cpp/releases/download/b10950/llama-b10950-bin-win-vulkan-x64.zip",
        "sha256": "787061f560eb2f14db7c03396cb56e59759b6dfccd162dc341b10cfa3bd5b779",
        "size": 31673509, "license": "MIT", "revision": LLAMA_TAG,
    },
    {
        "path": "models/Qwen3-4B-GGUF/Qwen3-4B-Q4_K_M.gguf",
        "url": hf("Qwen/Qwen3-4B-GGUF", QWEN_REV, "Qwen3-4B-Q4_K_M.gguf"),
        "sha256": "7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5",
        "size": 2497280256, "license": "Apache-2.0", "revision": QWEN_REV,
    },
    {
        "path": "models/bge-small-zh-v1.5/model.safetensors",
        "url": hf("BAAI/bge-small-zh-v1.5", BGE_REV, "model.safetensors"),
        "sha256": "354763b9b1357bc9c44f62c6be2276321081ed2567773608c0d0785b61d5a026",
        "size": 95827648, "license": "MIT", "revision": BGE_REV,
    },
]
for filename in ["config.json", "special_tokens_map.json", "tokenizer.json", "tokenizer_config.json", "vocab.txt", "README.md"]:
    ASSETS.append({"path": f"models/bge-small-zh-v1.5/{filename}", "url": hf("BAAI/bge-small-zh-v1.5", BGE_REV, filename), "license": "MIT", "revision": BGE_REV})
for filename in ["LICENSE", "README.md"]:
    ASSETS.append({"path": f"models/Qwen3-4B-GGUF/{filename}", "url": hf("Qwen/Qwen3-4B-GGUF", QWEN_REV, filename), "license": "Apache-2.0", "revision": QWEN_REV})
ASSETS.append({"path": "runtime/licenses/llama.cpp.LICENSE", "url": f"https://raw.githubusercontent.com/ggml-org/llama.cpp/{LLAMA_TAG}/LICENSE", "license": "MIT", "revision": LLAMA_TAG})


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def acquire(asset, offline=False):
    path = ROOT / asset["path"]
    expected = asset.get("sha256")
    if path.exists() and (not expected or sha256(path) == expected):
        return {**asset, "sha256": sha256(path), "size": path.stat().st_size, "verified": True}
    if offline:
        raise RuntimeError(f"Required file missing or checksum incorrect: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    offset = partial.stat().st_size if partial.exists() else 0
    headers = {"User-Agent": "signal-formula-rag/1.0"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(asset["url"], headers=headers)
    started = time.monotonic()
    print(f"Downloading {asset['path']} (resume={offset})", flush=True)
    with urllib.request.urlopen(request, timeout=90) as response:
        if offset and response.status != 206:
            offset = 0
        with partial.open("ab" if offset else "wb") as stream:
            last_report = time.monotonic()
            while chunk := response.read(4 * 1024 * 1024):
                stream.write(chunk)
                if time.monotonic() - last_report > 30:
                    print(f"Progress {asset['path']}: {stream.tell():,} bytes", flush=True)
                    last_report = time.monotonic()
    actual = sha256(partial)
    if expected and actual != expected:
        raise RuntimeError(f"SHA256 mismatch for {path.name}: {actual}")
    if asset.get("size") and partial.stat().st_size != asset["size"]:
        raise RuntimeError(f"Size mismatch for {path.name}")
    partial.replace(path)
    print(f"Verified {asset['path']} ({time.monotonic() - started:.1f}s)", flush=True)
    return {**asset, "sha256": actual, "size": path.stat().st_size, "verified": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Verify existing resources only; no external network")
    args = parser.parse_args()
    errors, results = [], []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(acquire, asset, args.offline): asset for asset in ASSETS}
        for future in concurrent.futures.as_completed(futures):
            try:
                results.append(future.result())
            except Exception as exc:
                errors.append({"path": futures[future]["path"], "error": str(exc)})
                print(f"ERROR {errors[-1]}", flush=True)
    report = {"assets": sorted(results, key=lambda item: item["path"]), "errors": errors}
    (ROOT / "runtime").mkdir(exist_ok=True)
    (ROOT / "runtime/assets_manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if errors:
        raise SystemExit(1)
    archive = ROOT / ASSETS[0]["path"]
    target = ROOT / f"runtime/llama.cpp-{LLAMA_TAG}"
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        # Validate resolved destination even for upstream archives.
        for member in bundle.infolist():
            dest = (target / member.filename).resolve()
            if not dest.is_relative_to(target.resolve()):
                raise RuntimeError("Unsafe archive path")
        bundle.extractall(target)
    print("Pinned runtime resources are ready.", flush=True)


if __name__ == "__main__":
    main()
