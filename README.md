# Valorant Aim Coach

A free desktop app that reviews one of your Valorant clips and tells you, with
numbers, how good your crosshair placement is.

It watches the clip, finds every moment an enemy first appears on screen,
measures how far your crosshair was from their head at that instant, and
compares you against a pool of professional match VODs. You get an HTML report
with your stats and specific things to work on.

Everything runs **locally on your PC**. No internet, no account, no upload of
your footage. The enemy detection and analysis models are bundled inside the
download.

---

## Download

**[Download the latest release](https://github.com/superhangy/valorant-crosshair-analyzer/releases/latest)**

Grab the `ValorantAimCoach-<date>.zip` file under "Assets".

- 64-bit Windows 10 or 11
- About 1 GB of free disk space, ~4 GB RAM
- No graphics card required

## How to use it

1. Unzip the whole folder somewhere (your Desktop is fine).
2. Double-click `ValorantAimCoach.exe`.
3. The first time, Windows may say *"Windows protected your PC"*. Click
   **More info -> Run anyway**. The app is unsigned (code-signing certificates
   cost money), not dangerous.
4. Click **Choose clip** and pick an `.mp4` of your gameplay. A Deathmatch clip
   works best; a full ranked match is fine too.
5. Click **Analyze** and wait. It takes roughly twice the length of the clip
   (a 20-minute clip is about 40 minutes). You can minimise it and do other
   things, just don't close it.
6. Part way through, a small window shows you a few frames and asks *"is this a
   real enemy?"* Click **Keep** or **Drop** for each.
7. When it finishes, the coaching report opens in your browser. It is also
   saved as `coaching_report.html` in a new `coach_<clipname>` folder right
   next to your clip.

## Troubleshooting

- **"0 reveals detected"** - the clip had little real combat, or the detector
  struggled with it. Try a Deathmatch clip.
- **Antivirus flags it** - it is a PyInstaller-packed Python app, which some
  scanners dislike. Add an exception for the folder, or check the file on
  virustotal.com.
- **Anything else** - the black console window shows a log; copy that when
  asking for help.

---

## How it works

| Stage | What happens |
|-------|--------------|
| Frame extraction | ffmpeg pulls frames from the clip |
| Enemy reveal detection | a YOLO detector finds when an enemy first becomes visible |
| Pre-flag filtering | three small classifiers drop false positives (teammates, gun viewmodel, non-enemy shapes) before you review |
| Manual spot-check | you confirm a handful of borderline frames |
| Crosshair measurement | pixel distance from crosshair to enemy head, converted to degrees |
| Baseline comparison | your numbers vs. a pool of ~100 filtered pro match VODs |
| Report | an HTML page with your stats and coaching notes |

The five model files ship inside the release zip, so the app works with no
setup and no network.

## Build from source

The app is packaged with PyInstaller. See `build_release.py` and
`aimcoach.spec`. You need Python 3.11+, the packages in
`requirements-build.txt` (CPU-only torch), plus ffmpeg and tesseract binaries
staged under `vendor/`.

```
py -3.14 -m venv .venv-build
.venv-build\Scripts\python -m pip install -r requirements-build.txt ^
    --extra-index-url https://download.pytorch.org/whl/cpu
.venv-build\Scripts\python build_release.py
```

To run the pipeline directly on a clip without building the app:
`python coach_clip.py --clip <clip.mp4>`.

## License

[MIT](LICENSE). Free to use, modify, and share; no warranty.
