# PyInstaller spec for the portable ValorantAimCoach (Windows, onedir).
# Build with the CPU-only venv:
#   .venv-build/Scripts/pyinstaller aimcoach.spec --noconfirm
# (or just run build_release.py, which also stages vendor/ + docs + zips).

from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH)

datas = []
binaries = []
hiddenimports = [
    "report_html",
    "predict_teammate_prob", "predict_gunmodel_prob", "predict_enemy_prob",
    "extract_ally_classifier_dataset", "calibrate_ally_filter",
    "extract_hard_negatives_from_review", "analyze_crosshair_placement",
    "app_paths",
    "PIL._tkinter_finder",
]

# ultralytics ships cfg yaml + needs a bunch of lazy submodules
for pkg in ("ultralytics",):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h

hiddenimports += collect_submodules("torchvision.models")

# --- bundled model weights (keep the same relative paths the code asks for) ---
MODELS = [
    "runs/detect/runs/valorant_head_gray_v1/weights/best.pt",
    "runs/detect/runs/valorant_enemy_v1-3/weights/best.pt",
    "ally_classifier_head.pt",
    "gunmodel_classifier_head.pt",
    "enemy_classifier_head.pt",
]
for rel in MODELS:
    src = ROOT / rel
    datas.append((str(src), str(Path(rel).parent)))

# --- pro baseline ---
datas.append((str(ROOT / "analysis_output" / "engagements_pooled.csv"), "analysis_output"))

# NOTE: vendor/ (ffmpeg, tesseract) is deliberately NOT bundled here.
# build_release.py copies it next to the exe so PyInstaller never scans the
# tesseract DLLs (which caused ~130 MB of duplication). app_paths.external_dir()
# finds it there.


a = Analysis(
    ["aimcoach_app.py"],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter.test",
        "notebook", "IPython", "jupyter",
        "polars", "_polars_runtime_32", "ultralytics_platform",
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ValorantAimCoach",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,          # keep a log window for v1 -- helps diagnose user issues
    disable_windowed_traceback=False,
    icon=str(ROOT / "app_icon.ico") if (ROOT / "app_icon.ico").exists() else None,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name="ValorantAimCoach",
)
