"""
Drop human-flagged false positives from an engagements.csv before it's used
in any trend/deviation report.

Refuses to run until every frame in the folder has a verdict in
<folder>_review.csv (run review_engagements.py first) - the point is that no
annotated batch ever gets used unreviewed.

Usage:
    python filter_engagements.py engagements_1000-iq-cypher-c9-oxy-cypher-valorant-ranked-gameplay

Writes engagements_filtered.csv into the same folder (only "good" rows kept,
same columns as engagements.csv). The original engagements.csv is left
untouched.
"""

import csv
import re
import sys
from pathlib import Path

TIMESTAMP_RE = re.compile(r"^t(\d+\.\d+)s\.jpg$")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python filter_engagements.py <engagements_folder>")

    folder = Path(sys.argv[1])
    engagements_csv = folder / "engagements.csv"
    review_csv = folder.parent / f"{folder.name}_review.csv"

    if not engagements_csv.exists():
        raise SystemExit(f"No engagements.csv found in {folder}")
    if not review_csv.exists():
        raise SystemExit(
            f"No review found at {review_csv}\n"
            f"Run this first: python review_engagements.py {folder}"
        )

    with open(engagements_csv, newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        engagements = list(reader)

    with open(review_csv, newline="") as f:
        verdicts = {row["filename"]: row["label"] for row in csv.DictReader(f)}

    def filename_for(row):
        return f"t{float(row['timestamp_s']):07.2f}s.jpg"

    missing = [filename_for(r) for r in engagements if filename_for(r) not in verdicts]
    if missing:
        raise SystemExit(
            f"{len(missing)} of {len(engagements)} frames in {folder} have not been "
            f"reviewed yet. Finish this first:\n"
            f"    python review_engagements.py {folder}"
        )

    kept = [r for r in engagements if verdicts[filename_for(r)] == "good"]
    dropped = len(engagements) - len(kept)

    out_path = folder / "engagements_filtered.csv"
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(kept)

    print(f"{len(kept)} kept, {dropped} dropped (confirmed false positives) -> {out_path}")


if __name__ == "__main__":
    main()
