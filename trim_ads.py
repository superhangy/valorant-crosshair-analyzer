"""Cut YouTube ad segments out of a recorded VOD before analysis.

Takes the ad start/end timestamps logged by the browser-side JS watcher
(window.__adEvents, seconds relative to when the watcher started) and
produces a version of the clip with those windows removed.
"""

import argparse
import json
import os
import subprocess
import tempfile

FFMPEG = r"C:\Users\alexh\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0-full_build\bin\ffmpeg.exe"
FFPROBE = FFMPEG.replace("ffmpeg.exe", "ffprobe.exe")


def get_duration(path):
    out = subprocess.check_output([
        FFPROBE, "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", path,
    ])
    return float(out.strip())


def build_keep_intervals(ad_intervals, duration, pad=0.5):
    padded = sorted([(max(0.0, s - pad), min(duration, e + pad)) for s, e in ad_intervals])
    merged = []
    for s, e in padded:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    keep = []
    cursor = 0.0
    for s, e in merged:
        if s > cursor:
            keep.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < duration:
        keep.append((cursor, duration))
    return [k for k in keep if k[1] - k[0] > 0.1]


def trim(input_path, output_path, ad_intervals):
    # Stream-copy only — no decode/re-encode. A filter_complex trim+concat
    # through h264_nvenc silently died partway through a 31GB/34min source
    # (audio kept muxing to full length, video froze at ~50s, exit code 0)
    # so this avoids the encoder pipeline entirely: cut each keep-interval
    # with -ss/-to before -i (fast keyframe seek, not frame-accurate — fine
    # given the 0.5s pad already applied) then concat losslessly.
    duration = get_duration(input_path)
    keep = build_keep_intervals(ad_intervals, duration)

    if not ad_intervals or (len(keep) == 1 and keep[0][0] == 0.0):
        subprocess.run([FFMPEG, "-y", "-i", input_path, "-c", "copy", output_path], check=True)
        return 0

    with tempfile.TemporaryDirectory(prefix="trim_ads_") as tmp_dir:
        segment_paths = []
        for i, (s, e) in enumerate(keep):
            seg_path = os.path.join(tmp_dir, f"seg{i}.mp4")
            cmd = [
                FFMPEG, "-y", "-ss", str(s), "-to", str(e), "-i", input_path,
                "-c", "copy", "-avoid_negative_ts", "make_zero", seg_path,
            ]
            subprocess.run(cmd, check=True)
            segment_paths.append(seg_path)

        list_path = os.path.join(tmp_dir, "concat_list.txt")
        with open(list_path, "w") as f:
            for p in segment_paths:
                f.write(f"file '{p}'\n")

        cmd = [FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", output_path]
        subprocess.run(cmd, check=True)

    return len(ad_intervals)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--ad-events", required=True, help="JSON string or path to a JSON file: [{\"start\":.., \"end\":..}, ...]")
    args = p.parse_args()

    src = args.ad_events
    events = json.load(open(src)) if os.path.exists(src) else json.loads(src)
    ad_intervals = [(ev["start"], ev["end"]) for ev in events if ev.get("end") is not None]

    n = trim(args.input, args.output, ad_intervals)
    print(f"Trimmed {n} ad segment(s). Output: {args.output}")
