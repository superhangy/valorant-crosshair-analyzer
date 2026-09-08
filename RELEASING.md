# Releasing / maintainer notes

Status and steps for cutting a new build of the portable **ValorantAimCoach**
app. Not needed to *use* the app — see [README](README.md) for that.

## Current state (2026-09-07)

- **v0.1 is public.** Repo is public, MIT licensed. The release lives at
  `releases/latest` with `ValorantAimCoach-20260907.zip` attached (433 MB
  compressed, ~1 GB unpacked).
- The five model files (`ally/enemy/gunmodel_classifier_head.pt`, the two
  `runs/detect/.../best.pt` detectors) are committed and also bundled in the
  zip. The app runs fully offline.
- `gh` CLI is authenticated on the maintainer machine, so future releases are
  one command.

## Known gaps

- **Not human click-tested end to end.** The frozen exe passes `--selftest` and
  a headless `--clip` run, and the Tk/Reviewer wiring passes a headless test,
  but nobody has driven the actual GUI (choose clip -> Analyze -> keep/drop
  popup -> report) start to finish. First real run is the proof.
- Bundle size: torch ~317 MB, ffmpeg ~99 MB. Both are trimmable later if the
  download size becomes a problem.

## Build a new zip

Needs the build venv (CPU torch) and `vendor/` (ffmpeg + tesseract binaries),
neither of which is in git.

```
py -3.14 -m venv .venv-build
.venv-build\Scripts\python -m pip install -r requirements-build.txt ^
    --extra-index-url https://download.pytorch.org/whl/cpu
# populate vendor/ with ffmpeg essentials + tesseract (see build_release.py)
.venv-build\Scripts\python build_release.py
```

Output: `ValorantAimCoach-<date>.zip` in the repo root (gitignored).

Smoke-check the frozen exe before shipping:

```
build\dist\ValorantAimCoach\ValorantAimCoach.exe --selftest
build\dist\ValorantAimCoach\ValorantAimCoach.exe --clip some_clip.mp4 --headless
```

## Cut the release

```
gh release create vX.Y ValorantAimCoach-<date>.zip ^
    --title "Valorant Aim Coach vX.Y" ^
    --notes-file notes.md ^
    --latest
```

Then update the date in the README download filename reference if it changed.

Hidden exe flags for testing: `--selftest`, `--clip <path>`, `--headless`,
`--reanalyze`, `--rescore`.
