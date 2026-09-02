# Pro-baseline crosshair-discipline analysis.
#
# This is the payoff step of the whole project. Every earlier stage just
# produced clean data: 76 reviewed pro VODs, each with an
# engagements_filtered.csv listing every enemy-reveal moment and how far the
# crosshair was from the enemy's head at that moment (as a percentage of
# screen width -- smaller is better pre-aim).
#
# Here we pool all of that and actually answer questions:
#   - What does "good crosshair placement" look like numerically for pros?
#   - Does it vary by agent (duelists peek more aggressively) or map?
#   - Which individual reveals were unusually bad even for a pro (outliers)?
#   - How much does smoke on the sightline hurt pre-aim?
#
# The learner's own recorded matches can later be run through the same
# analyze_crosshair_placement.py pipeline and compared against these numbers
# -- that comparison is the "coaching feedback" the project is ultimately for.
#
# Java note: this file is plain top-to-bottom procedural code. Think of each
# `def` as a static method and the dicts as HashMap<String, ...>. No classes
# needed at this size.

import csv
import glob
import os
import re
import statistics
from collections import defaultdict

import matplotlib

matplotlib.use("Agg")  # write PNG files, never open a window
import matplotlib.pyplot as plt

OUT_DIR = "analysis_output"

# An engagement at or below this crosshair-to-head distance (percent of screen
# width) counts as "pre-aimed" -- you were already on the spot, just click.
# 5% of a 2560px-wide screen is ~128px, roughly a head's width at mid range.
DISCIPLINED_THRESHOLD_PCT = 5.0

# ---------------------------------------------------------------------------
# Metadata parsing: pull player / agent / map out of the folder-name slug.
# Slugs look like: engagements_30-kills-mvp-c9-oxy-jett-valorant-radiant-...
# These lists are matched as whole hyphen-delimited tokens against the slug.
# ---------------------------------------------------------------------------

AGENTS = [
    "jett", "raze", "neon", "phoenix", "yoru", "reyna", "iso", "waylay",
    "sova", "fade", "breach", "skye", "kayo", "gekko",
    "killjoy", "cypher", "sage", "chamber", "deadlock", "vyse",
    "brimstone", "omen", "viper", "astra", "harbor", "clove",
]
# "kay-o" in slugs -> normalize to "kayo"
AGENT_ALIASES = {"kay-o": "kayo"}

MAPS = [
    "bind", "haven", "split", "ascent", "icebox", "breeze", "fracture",
    "pearl", "lotus", "sunset", "abyss", "corrode",
]

# Known player handles that appear in this channel's titles.
PLAYERS = [
    "oxy", "asuna", "cryo", "demon1", "aspas", "s0m", "zekken", "derrek",
    "florescent", "aleksandar", "eggsterr", "primmie", "ion", "nats",
    "sato", "less",
]

DUELISTS = {"jett", "raze", "neon", "phoenix", "yoru", "reyna", "iso"}


def parse_meta(slug):
    """slug (folder name minus 'engagements_') -> {player, agent, map, role}."""
    s = slug.lower()
    for alias, canon in AGENT_ALIASES.items():
        s = s.replace(alias, canon)
    tokens = set(s.split("-"))

    agent = next((a for a in AGENTS if a in tokens), None)
    map_name = next((m for m in MAPS if m in tokens), None)
    player = next((p for p in PLAYERS if p in tokens), None)

    role = None
    if agent:
        role = "duelist" if agent in DUELISTS else "non-duelist"

    return {"player": player, "agent": agent, "map": map_name, "role": role}


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_all():
    """Return a list of engagement dicts, one per row across every video."""
    engagements = []
    videos = []
    for path in sorted(glob.glob("engagements_*/engagements_filtered.csv")):
        folder = os.path.dirname(path)
        slug = folder[len("engagements_"):]
        if "spotcheck_backup" in slug:
            continue  # corrupted 3-frame leftover, not real data

        meta = parse_meta(slug)
        n_before = len(engagements)
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                try:
                    dist = float(row["distance_pct_width"])
                except (KeyError, ValueError):
                    continue
                smoke = str(row.get("smoke_present", "")).strip().lower() == "true"
                engagements.append({
                    "slug": slug,
                    "timestamp_s": _safe_float(row.get("timestamp_s")),
                    "distance_pct": dist,
                    "confidence": _safe_float(row.get("confidence")),
                    "smoke": smoke,
                    **meta,
                })
        videos.append({
            "slug": slug,
            "n": len(engagements) - n_before,
            **meta,
        })
    return engagements, videos


def _safe_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def summarize(values):
    """Distance distribution summary for a list of engagement distances."""
    if not values:
        return None
    v = sorted(values)
    n = len(v)
    return {
        "n": n,
        "mean": statistics.mean(v),
        "median": statistics.median(v),
        "p25": _pct(v, 25),
        "p75": _pct(v, 75),
        "p90": _pct(v, 90),
        "best": v[0],
        "worst": v[-1],
        "disciplined_pct": 100.0 * sum(1 for x in v if x <= DISCIPLINED_THRESHOLD_PCT) / n,
    }


def _pct(sorted_vals, p):
    """Simple nearest-rank percentile (no interpolation -- easy to explain)."""
    if not sorted_vals:
        return None
    k = max(0, min(len(sorted_vals) - 1, round(p / 100 * (len(sorted_vals) - 1))))
    return sorted_vals[k]


def group_summary(engagements, key):
    """{key value -> distance summary}, skipping rows where the key is None."""
    buckets = defaultdict(list)
    for e in engagements:
        if e[key] is not None:
            buckets[e[key]].append(e["distance_pct"])
    return {k: summarize(v) for k, v in buckets.items()}


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def chart_histogram(engagements):
    dists = [e["distance_pct"] for e in engagements]
    plt.figure(figsize=(9, 5))
    plt.hist(dists, bins=60, range=(0, 40), color="#4c72b0", edgecolor="white")
    med = statistics.median(dists)
    plt.axvline(med, color="#c44e52", linestyle="--", label=f"median {med:.1f}%")
    plt.axvline(DISCIPLINED_THRESHOLD_PCT, color="#55a868", linestyle=":",
                label=f"pre-aim threshold {DISCIPLINED_THRESHOLD_PCT:.0f}%")
    plt.xlabel("crosshair-to-head distance at reveal (% of screen width)")
    plt.ylabel("number of engagements")
    plt.title(f"Pro crosshair placement -- {len(dists)} engagements, 76 VODs")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, "preaim_distribution_all.png"), dpi=110)
    plt.close()


def chart_group_bars(summ_by_group, title, filename, min_n=20):
    items = [(k, s) for k, s in summ_by_group.items() if s and s["n"] >= min_n]
    items.sort(key=lambda kv: kv[1]["median"])
    if not items:
        return
    labels = [f"{k} (n={s['n']})" for k, s in items]
    medians = [s["median"] for k, s in items]
    plt.figure(figsize=(9, max(3, 0.45 * len(items) + 1)))
    plt.barh(labels, medians, color="#4c72b0")
    plt.xlabel("median crosshair-to-head distance (% of screen width)")
    plt.title(title)
    plt.gca().invert_yaxis()
    plt.tight_layout()
    plt.savefig(os.path.join(OUT_DIR, filename), dpi=110)
    plt.close()


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def fmt_summary_row(label, s):
    return (f"| {label} | {s['n']} | {s['median']:.2f} | {s['mean']:.2f} | "
            f"{s['p90']:.2f} | {s['worst']:.2f} | {s['disciplined_pct']:.0f}% |")


def write_report(engagements, videos):
    all_summary = summarize([e["distance_pct"] for e in engagements])
    clear = summarize([e["distance_pct"] for e in engagements if not e["smoke"]])
    smoky = summarize([e["distance_pct"] for e in engagements if e["smoke"]])

    by_agent = group_summary(engagements, "agent")
    by_map = group_summary(engagements, "map")
    by_player = group_summary(engagements, "player")
    by_role = group_summary(engagements, "role")

    # per-video summaries
    vid_summaries = {}
    for v in videos:
        rows = [e["distance_pct"] for e in engagements if e["slug"] == v["slug"]]
        vid_summaries[v["slug"]] = summarize(rows)

    # global worst individual reveals
    worst = sorted(engagements, key=lambda e: -e["distance_pct"])[:25]

    # per-video outliers: reveals worse than that video's own 90th percentile
    # AND above the disciplined threshold -- "bad even by this player's standard"
    outliers = []
    for v in videos:
        s = vid_summaries[v["slug"]]
        if not s or s["n"] < 8:
            continue
        for e in engagements:
            if e["slug"] == v["slug"] and e["distance_pct"] > max(s["p90"], 15.0):
                outliers.append(e)
    outliers.sort(key=lambda e: -e["distance_pct"])

    lines = []
    w = lines.append
    w("# Pro Crosshair-Discipline Baseline\n")
    w(f"_Generated from {len(videos)} reviewed pro VODs, "
      f"{len(engagements)} filtered enemy-reveal engagements._\n")
    w("Every number below is **crosshair-to-head distance at the moment the "
      "enemy became visible**, as a percent of screen width. Lower = better "
      "pre-aim (you were already looking there). This is the yardstick the "
      "learner's own matches get measured against.\n")

    w("## Headline numbers\n")
    w("| Set | n | median | mean | p90 | worst | pre-aimed (<=5%) |")
    w("|---|---|---|---|---|---|---|")
    w(fmt_summary_row("All engagements", all_summary))
    w(fmt_summary_row("Clear sightline", clear))
    if smoky:
        w(fmt_summary_row("Smoke near target", smoky))
    w("")
    w(f"- A pro's **median** reveal is **{all_summary['median']:.1f}%** of "
      f"screen width from the head -- essentially already on target.")
    w(f"- **{all_summary['disciplined_pct']:.0f}%** of pro engagements are "
      f"pre-aimed (within {DISCIPLINED_THRESHOLD_PCT:.0f}%).")
    if smoky:
        pen = smoky["median"] - clear["median"]
        w(f"- Smoke on the sightline costs about **{pen:+.1f}%** median "
          f"distance ({clear['median']:.1f}% -> {smoky['median']:.1f}%).")
    w("")

    w("## By agent role\n")
    w("| Role | n | median | mean | p90 | worst | pre-aimed |")
    w("|---|---|---|---|---|---|---|")
    for role in ("duelist", "non-duelist"):
        if by_role.get(role):
            w(fmt_summary_row(role, by_role[role]))
    w("")

    w("## By agent (>=20 engagements)\n")
    w("| Agent | n | median | mean | p90 | worst | pre-aimed |")
    w("|---|---|---|---|---|---|---|")
    for k, s in sorted(by_agent.items(), key=lambda kv: kv[1]["median"] if kv[1] else 1e9):
        if s and s["n"] >= 20:
            w(fmt_summary_row(k, s))
    w("")

    w("## By map (>=20 engagements)\n")
    w("| Map | n | median | mean | p90 | worst | pre-aimed |")
    w("|---|---|---|---|---|---|---|")
    for k, s in sorted(by_map.items(), key=lambda kv: kv[1]["median"] if kv[1] else 1e9):
        if s and s["n"] >= 20:
            w(fmt_summary_row(k, s))
    w("")

    w("## By player (>=20 engagements)\n")
    w("| Player | n | median | mean | p90 | worst | pre-aimed |")
    w("|---|---|---|---|---|---|---|")
    for k, s in sorted(by_player.items(), key=lambda kv: kv[1]["median"] if kv[1] else 1e9):
        if s and s["n"] >= 20:
            w(fmt_summary_row(k, s))
    w("")

    w("## Best and worst VODs by median pre-aim (>=15 engagements)\n")
    ranked = sorted(
        ((slug, s) for slug, s in vid_summaries.items() if s and s["n"] >= 15),
        key=lambda kv: kv[1]["median"],
    )
    w("| VOD | n | median | mean | worst |")
    w("|---|---|---|---|---|")
    for slug, s in ranked[:5]:
        w(f"| {slug} | {s['n']} | {s['median']:.2f} | {s['mean']:.2f} | {s['worst']:.2f} |")
    w("| ... | | | | |")
    for slug, s in ranked[-5:]:
        w(f"| {slug} | {s['n']} | {s['median']:.2f} | {s['mean']:.2f} | {s['worst']:.2f} |")
    w("")

    w("## 25 worst individual reveals across all VODs\n")
    w("These are candidates for a manual eyeball: a genuine bad flick, or a "
      "detector false-positive that slipped through review.\n")
    w("| distance % | VOD | timestamp (s) | agent | map | smoke |")
    w("|---|---|---|---|---|---|")
    for e in worst:
        ts = f"{e['timestamp_s']:.1f}" if e["timestamp_s"] is not None else "?"
        w(f"| {e['distance_pct']:.1f} | {e['slug']} | {ts} | "
          f"{e['agent'] or '?'} | {e['map'] or '?'} | {'yes' if e['smoke'] else ''} |")
    w("")

    w(f"## Per-video outliers ({len(outliers)} total)\n")
    w("Reveals worse than their own video's 90th percentile *and* above 15%. "
      "'Bad even by that player's standard in that match.'\n")
    w("| distance % | VOD | timestamp (s) | agent | map |")
    w("|---|---|---|---|---|")
    for e in outliers[:40]:
        ts = f"{e['timestamp_s']:.1f}" if e["timestamp_s"] is not None else "?"
        w(f"| {e['distance_pct']:.1f} | {e['slug']} | {ts} | "
          f"{e['agent'] or '?'} | {e['map'] or '?'} |")
    if len(outliers) > 40:
        w(f"| ... {len(outliers) - 40} more ... | | | | |")
    w("")

    w("## Files\n")
    w("- `analysis_output/preaim_distribution_all.png` -- overall histogram")
    w("- `analysis_output/by_agent.png`, `by_map.png`, `by_player.png` -- median bars")
    w("- `analysis_output/engagements_pooled.csv` -- every engagement, one row, with parsed metadata")
    w("")

    with open(os.path.join(OUT_DIR, "pro_baseline_report.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def write_pooled_csv(engagements):
    path = os.path.join(OUT_DIR, "engagements_pooled.csv")
    cols = ["slug", "player", "agent", "map", "role", "timestamp_s",
            "distance_pct", "confidence", "smoke"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        wtr = csv.DictWriter(fh, fieldnames=cols)
        wtr.writeheader()
        for e in engagements:
            wtr.writerow({c: e.get(c) for c in cols})


# ---------------------------------------------------------------------------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    engagements, videos = load_all()
    if not engagements:
        print("No filtered engagement data found.")
        return

    print(f"Loaded {len(engagements)} engagements from {len(videos)} VODs.")
    unmatched_agent = sum(1 for v in videos if v["agent"] is None)
    unmatched_map = sum(1 for v in videos if v["map"] is None)
    unmatched_player = sum(1 for v in videos if v["player"] is None)
    print(f"  metadata gaps: agent {unmatched_agent}, map {unmatched_map}, "
          f"player {unmatched_player} (of {len(videos)} VODs)")

    chart_histogram(engagements)
    chart_group_bars(group_summary(engagements, "agent"),
                     "Median pre-aim by agent", "by_agent.png")
    chart_group_bars(group_summary(engagements, "map"),
                     "Median pre-aim by map", "by_map.png")
    chart_group_bars(group_summary(engagements, "player"),
                     "Median pre-aim by player", "by_player.png")
    write_pooled_csv(engagements)
    write_report(engagements, videos)
    print(f"Wrote report + charts to {OUT_DIR}/")


if __name__ == "__main__":
    main()
