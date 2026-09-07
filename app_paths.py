"""
Path resolution that works both from a normal source checkout and from a
frozen PyInstaller bundle (the portable ValorantAimCoach build).

Every module that needs a bundled resource -- model weights, ffmpeg,
tesseract, the pooled pro baseline -- should ask for it here instead of
hardcoding an absolute Windows path.

    from app_paths import resource_path, ffmpeg_exe, tesseract_exe

    HEAD_MODEL_PATH = str(resource_path("runs/detect/runs/valorant_head_gray_v1/weights/best.pt"))

When frozen, PyInstaller unpacks bundled data under sys._MEIPASS; when not,
resources sit next to this file in the repo. An env var override wins over
both, so a power user (or a test) can point at a different file without
rebuilding.
"""

import os
import sys
import shutil
from pathlib import Path


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def base_dir() -> Path:
    """Root for resources bundled *inside* the PyInstaller archive
    (models, the pooled csv) -- _MEIPASS when frozen, repo root otherwise."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def external_dir() -> Path:
    """Directory that sits *next to* the exe (onedir) -- where big external
    tools like vendor/ffmpeg and vendor/tesseract are kept unpacked, so
    PyInstaller never has to scan their DLLs. Repo root when not frozen."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_path(relative: str) -> Path:
    return base_dir() / relative


def _search_roots():
    seen = []
    for d in (external_dir(), base_dir()):
        if d not in seen:
            seen.append(d)
    return seen


def _from_env_or_which(env_var: str, exe_name: str, bundled_rel: str) -> str:
    override = os.environ.get(env_var)
    if override and Path(override).exists():
        return override
    for root in _search_roots():
        cand = root / bundled_rel
        if cand.exists():
            return str(cand)
    found = shutil.which(exe_name)
    if found:
        return found
    # Last resort: return the expected path anyway so the error message
    # points somewhere useful.
    return str(external_dir() / bundled_rel)


def ffmpeg_exe() -> str:
    return _from_env_or_which("AIMCOACH_FFMPEG", "ffmpeg", "vendor/ffmpeg/ffmpeg.exe")


_TESSERACT_FALLBACKS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def tesseract_exe() -> str:
    found = _from_env_or_which(
        "AIMCOACH_TESSERACT", "tesseract", "vendor/tesseract/tesseract.exe"
    )
    if Path(found).exists():
        return found
    for cand in _TESSERACT_FALLBACKS:
        if Path(cand).exists():
            return cand
    return found


def tessdata_dir() -> "str | None":
    """Directory holding eng.traineddata, if bundled. None -> let tesseract
    use its own default lookup."""
    d = resource_path("vendor/tesseract/tessdata")
    return str(d) if d.exists() else os.environ.get("TESSDATA_PREFIX")
