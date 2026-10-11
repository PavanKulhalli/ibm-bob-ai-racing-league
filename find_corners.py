#!/usr/bin/env python3
"""find_corners.py — Lap-segment analyser for gym_torcs telemetry.

Reads lap_data.csv and lap_summary.csv (built-in libraries only).
Identifies candidate corner zones and straight zones from forward_track
sensor readings, groups consecutive samples into contiguous segments,
and prints a human-readable report.

Usage examples (Mac):
    python3 find_corners.py --list
    python3 find_corners.py --run 20261009_173451Z_e16440e5 --episode ep_734ba673 --lap 1
    python3 find_corners.py --run 20261009_173451Z_e16440e5

IMPORTANT — thresholds are heuristic, NOT exact:
  • forward_track < CORNER_THRESH (40 m)  → candidate corner zone
  • forward_track > STRAIGHT_THRESH (150 m) → candidate straight zone
  forward_track is the single dead-ahead sensor (0°, index 9).  It reports
  distance to the nearest surface boundary in that exact direction.  It does
  NOT measure lateral clearance or safe cornering radius.  A value of 35 m
  means a wall or track edge is 35 m ahead in a straight line; the car may
  still have plenty of room if the track curves.  Blank / invalid readings
  are excluded from zone membership but counted and flagged.
"""

import argparse
import csv
import math
import sys
from collections import defaultdict

# ---------------------------------------------------------------------------
# Thresholds (change here to experiment — no driving code is modified)
# ---------------------------------------------------------------------------
CORNER_THRESH   = 40.0    # m  forward_track below this → candidate corner
STRAIGHT_THRESH = 150.0   # m  forward_track above this → candidate straight
MIN_ZONE_SAMPLES = 3      # ignore zones shorter than this many samples
GAP_WARN_DELTA   = 5      # warn if consecutive steps differ by more than this

# ---------------------------------------------------------------------------
# Required columns
# ---------------------------------------------------------------------------
REQUIRED_DATA_COLS = {
    "run_id", "episode_id", "lap_id", "lap_status",
    "step", "distFromStart", "distRaced", "curLapTime",
    "speedX", "trackPos", "angle",
    "forward_track", "min_valid_track", "damage",
}
REQUIRED_SUMMARY_COLS = {
    "run_id", "episode_id", "lap_id",
    "status", "lap_time", "damage_start", "damage_end",
    "max_speed", "completion_reason",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(val):
    """Return float or None for blank / non-numeric / ±inf / NaN values."""
    if val is None or val == "":
        return None
    try:
        f = float(val)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(f):
        return None
    return f


def _is_valid_forward_track(val):
    """forward_track is valid only when it is a finite positive number."""
    f = _to_float(val)
    return f is not None and f > 0


def _is_valid_speed(val):
    """speedX is valid when finite; negative values (reversing) are valid."""
    return _to_float(val) is not None


def _is_valid_track_pos(val):
    """trackPos is valid when finite; ±1 = road edge, >±1 = off road."""
    return _to_float(val) is not None


def _deg(rad_val):
    """Convert radians string/float to formatted degrees string."""
    f = _to_float(rad_val)
    if f is None:
        return "—"
    return f"{math.degrees(f):+.1f}°"


def _fmt(val, fmt=".1f", unit=""):
    f = _to_float(val)
    if f is None:
        return "—"
    return f"{f:{fmt}}{unit}"


def _lap_status_label(status, damage_start, damage_end, lap_time):
    """Produce a human-readable lap classification from summary columns."""
    parts = []
    if status == "completed":
        parts.append("COMPLETED")
    elif status == "partial":
        parts.append("PARTIAL (lap not finished)")
    elif status == "warmup":
        parts.append("WARMUP (before first finish-line crossing)")
    else:
        parts.append(status.upper() if status else "UNKNOWN")

    ds = _to_float(damage_start)
    de = _to_float(damage_end)
    if ds is not None and de is not None and de > ds:
        parts.append(f"DAMAGED (+{de - ds:.0f} pts during lap)")
    elif de is not None and de > 0:
        parts.append(f"damage={de:.0f} pts at end")

    if lap_time and _to_float(lap_time) is not None:
        t = _to_float(lap_time)
        parts.append(f"lap_time={t:.3f}s")

    return " | ".join(parts)


# ---------------------------------------------------------------------------
# CSV loading
# ---------------------------------------------------------------------------

def load_summary(path):
    """Return list of dicts from lap_summary.csv; validate columns."""
    rows = []
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            missing = REQUIRED_SUMMARY_COLS - set(reader.fieldnames or [])
            if missing:
                sys.exit(
                    f"ERROR: lap_summary.csv is missing required columns: "
                    f"{sorted(missing)}\n"
                    f"  Found: {sorted(reader.fieldnames or [])}"
                )
            for row in reader:
                rows.append(row)
    except FileNotFoundError:
        sys.exit(f"ERROR: lap_summary.csv not found at '{path}'")
    return rows


def load_data_for_lap(path, run_id, episode_id, lap_id):
    """Stream lap_data.csv and return only rows matching the selected lap.

    Validates columns on first read.  Rejects rows with a step number
    gap > GAP_WARN_DELTA and flags them.  Returns (rows, warnings).
    """
    rows = []
    warnings = []
    prev_step = None
    validated = False

    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            if not validated:
                missing = REQUIRED_DATA_COLS - set(reader.fieldnames or [])
                if missing:
                    sys.exit(
                        f"ERROR: lap_data.csv is missing required columns: "
                        f"{sorted(missing)}\n"
                        f"  Found: {sorted(reader.fieldnames or [])}"
                    )
                validated = True

            for raw in reader:
                if raw["run_id"] != run_id:
                    continue
                if raw["episode_id"] != episode_id:
                    continue
                if raw["lap_id"] != str(lap_id):
                    continue

                # --- validate sensor values ---
                bad = []
                fwd = _to_float(raw["forward_track"])
                if raw["forward_track"] != "" and fwd is None:
                    bad.append(f"forward_track='{raw['forward_track']}'")
                spd = _to_float(raw["speedX"])
                if raw["speedX"] != "" and spd is None:
                    bad.append(f"speedX='{raw['speedX']}'")
                tp = _to_float(raw["trackPos"])
                if raw["trackPos"] != "" and tp is None:
                    bad.append(f"trackPos='{raw['trackPos']}'")
                dmg = _to_float(raw["damage"])
                if raw["damage"] != "" and dmg is None:
                    bad.append(f"damage='{raw['damage']}'")

                if bad:
                    warnings.append(
                        f"  Step {raw['step']}: invalid sensor value(s) "
                        f"ignored — {', '.join(bad)}"
                    )
                    # still include the row; affected fields treated as blank

                # --- step-gap check ---
                step = _to_float(raw["step"])
                if step is not None:
                    step = int(step)
                    if prev_step is not None and (step - prev_step) > GAP_WARN_DELTA:
                        warnings.append(
                            f"  Step gap detected: {prev_step} → {step} "
                            f"({step - prev_step} steps missing)"
                        )
                    prev_step = step

                rows.append(raw)
    except FileNotFoundError:
        sys.exit(f"ERROR: lap_data.csv not found at '{path}'")

    return rows, warnings


# ---------------------------------------------------------------------------
# Zone detection
# ---------------------------------------------------------------------------

def _zone_type(fwd_val):
    """Classify a single sample's zone type from forward_track.

    Returns 'corner', 'straight', 'mid', or None (invalid/blank).
    """
    f = _to_float(fwd_val)
    if f is None or f <= 0:
        return None          # blank / invalid — excluded from zones
    if f < CORNER_THRESH:
        return "corner"
    if f > STRAIGHT_THRESH:
        return "straight"
    return "mid"             # between thresholds — not categorised


def detect_zones(rows, zone_type_filter):
    """Find contiguous runs of samples matching zone_type_filter.

    zone_type_filter: 'corner' or 'straight'

    Returns a list of zone dicts, each containing aggregated statistics.
    Handles start-line wraparound: when distFromStart drops sharply
    (by > 500 m relative to the previous sample), the segment is noted
    as crossing the start line.
    """
    zones = []
    current = None
    prev_dist = None

    for row in rows:
        zt = _zone_type(row["forward_track"])
        dist = _to_float(row["distFromStart"])
        dist_r = _to_float(row["distRaced"])
        spd = _to_float(row["speedX"])
        tp = _to_float(row["trackPos"])
        ang = _to_float(row["angle"])
        fwd = _to_float(row["forward_track"])
        mvt = _to_float(row["min_valid_track"])
        dmg = _to_float(row["damage"])
        step = _to_float(row["step"])

        # detect wraparound
        wrapped = (
            prev_dist is not None
            and dist is not None
            and (prev_dist - dist) > 500.0
        )
        if dist is not None:
            prev_dist = dist

        if zt == zone_type_filter:
            if current is None:
                current = _new_zone(row, dist, dist_r, spd, tp, ang, fwd, mvt, dmg, step)
                if wrapped:
                    current["crossed_start_line"] = True
            else:
                if wrapped:
                    current["crossed_start_line"] = True
                _extend_zone(current, row, dist, dist_r, spd, tp, ang, fwd, mvt, dmg, step)
        else:
            if current is not None:
                if len(current["steps"]) >= MIN_ZONE_SAMPLES:
                    zones.append(current)
                current = None

    # flush last open zone
    if current is not None and len(current["steps"]) >= MIN_ZONE_SAMPLES:
        zones.append(current)

    return zones


def _new_zone(row, dist, dist_r, spd, tp, ang, fwd, mvt, dmg, step):
    z = {
        "dist_start":       dist,
        "dist_r_start":     dist_r,
        "dist_end":         dist,
        "dist_r_end":       dist_r,
        "steps":            [step] if step is not None else [],
        "speeds":           [spd] if spd is not None else [],
        "trackPos_vals":    [tp] if tp is not None else [],
        "angle_vals":       [ang] if ang is not None else [],
        "fwd_vals":         [fwd] if fwd is not None else [],
        "mvt_vals":         [mvt] if mvt is not None else [],
        "damage_start":     dmg,
        "damage_end":       dmg,
        "invalid_fwd_count": 0,
        "crossed_start_line": False,
        "lap_status_vals":  [row.get("lap_status", "")],
    }
    return z


def _extend_zone(z, row, dist, dist_r, spd, tp, ang, fwd, mvt, dmg, step):
    if dist is not None:
        z["dist_end"] = dist
    if dist_r is not None:
        z["dist_r_end"] = dist_r
    if step is not None:
        z["steps"].append(step)
    if spd is not None:
        z["speeds"].append(spd)
    if tp is not None:
        z["trackPos_vals"].append(tp)
    if ang is not None:
        z["angle_vals"].append(ang)
    if fwd is not None:
        z["fwd_vals"].append(fwd)
    if mvt is not None:
        z["mvt_vals"].append(mvt)
    if dmg is not None:
        z["damage_end"] = dmg
    z["lap_status_vals"].append(row.get("lap_status", ""))


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------

def _zone_report(zones, zone_label, thresh_description):
    lines = []
    lines.append(f"\n{'='*70}")
    lines.append(f"  {zone_label.upper()} ZONES  ({thresh_description})")
    lines.append(f"  Threshold is heuristic — sensor measures straight-line")
    lines.append(f"  distance to nearest boundary in the dead-ahead direction only.")
    lines.append(f"{'='*70}")

    if not zones:
        lines.append(f"  No {zone_label} zones found (threshold: {thresh_description}).")
        return "\n".join(lines)

    for i, z in enumerate(zones, 1):
        n = len(z["steps"])
        speeds = z["speeds"]
        fwd_vals = z["fwd_vals"]
        mvt_vals = z["mvt_vals"]
        tp_vals = z["trackPos_vals"]
        ang_vals = z["angle_vals"]

        # distance
        d_s = z["dist_start"]
        d_e = z["dist_end"]
        dr_s = z["dist_r_start"]
        dr_e = z["dist_r_end"]

        dist_str = (
            f"{d_s:.1f}–{d_e:.1f} m (distFromStart)"
            if d_s is not None and d_e is not None
            else "— m"
        )
        dr_str = (
            f"  distRaced {dr_s:.1f}–{dr_e:.1f} m"
            if dr_s is not None and dr_e is not None
            else ""
        )

        # speed
        if speeds:
            spd_min = min(speeds)
            spd_max = max(speeds)
            spd_mean = sum(speeds) / len(speeds)
            speed_str = f"{spd_min:.1f} / {spd_mean:.1f} / {spd_max:.1f} km/h"
        else:
            speed_str = "—"

        # forward track
        if fwd_vals:
            fwd_min = min(fwd_vals)
            fwd_max = max(fwd_vals)
            fwd_str = f"{fwd_min:.1f}–{fwd_max:.1f} m"
        else:
            fwd_str = "—"

        # min_valid_track
        if mvt_vals:
            mvt_min = min(mvt_vals)
            mvt_str = f"{mvt_min:.1f} m (narrowest multi-angle reading)"
        else:
            mvt_str = "— (all blank — sensors off-road or pointing at wall)"

        # trackPos
        if tp_vals:
            tp_min = min(tp_vals)
            tp_max = max(tp_vals)
            tp_str = f"{tp_min:+.3f} to {tp_max:+.3f}  (0=centre, ±1=road edge)"
        else:
            tp_str = "—"

        # heading (angle)
        if ang_vals:
            ang_min = min(ang_vals)
            ang_max = max(ang_vals)
            ang_str = (
                f"{math.degrees(ang_min):+.1f}° to {math.degrees(ang_max):+.1f}°"
                f"  (0=aligned, +left, −right)"
            )
        else:
            ang_str = "—"

        # damage
        dmg_s = z["damage_start"]
        dmg_e = z["damage_end"]
        if dmg_s is not None and dmg_e is not None:
            delta = dmg_e - dmg_s
            if delta > 0:
                dmg_str = f"{dmg_s:.0f} → {dmg_e:.0f}  ⚠  +{delta:.0f} pts during zone"
            else:
                dmg_str = f"{dmg_e:.0f} pts (no increase)"
        else:
            dmg_str = "—"

        # lap status variety
        statuses = sorted(set(s for s in z["lap_status_vals"] if s))
        status_str = ", ".join(statuses) if statuses else "—"

        # step gap check
        gap_flag = ""
        steps = z["steps"]
        if len(steps) > 1:
            gaps = [steps[k+1] - steps[k] for k in range(len(steps)-1)
                    if steps[k] is not None and steps[k+1] is not None]
            big_gaps = [g for g in gaps if g > GAP_WARN_DELTA]
            if big_gaps:
                gap_flag = f"  ⚠  {len(big_gaps)} step gap(s) > {GAP_WARN_DELTA}"

        wrap_flag = "  ⚠  Crossed start/finish line" if z["crossed_start_line"] else ""

        lines.append(f"\n  Zone {i}{wrap_flag}")
        lines.append(f"    distFromStart : {dist_str}")
        if dr_str:
            lines.append(f"    {dr_str}")
        lines.append(f"    Samples       : {n}{gap_flag}")
        lines.append(f"    lap_status    : {status_str}")
        lines.append(f"    Speed min/avg/max : {speed_str}")
        lines.append(f"    forward_track : {fwd_str}  ← straight-line, dead-ahead only")
        lines.append(f"    min_valid_track: {mvt_str}")
        lines.append(f"    trackPos      : {tp_str}")
        lines.append(f"    Heading (angle): {ang_str}")
        lines.append(f"    Damage        : {dmg_str}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# List mode
# ---------------------------------------------------------------------------

def list_available(summary_rows, data_path):
    """Print all available run/episode/lap combinations."""
    print("\nAvailable laps in lap_summary.csv:\n")
    print(f"  {'run_id':<35} {'episode_id':<16} {'lap':>3}  {'status':<12}  "
          f"{'experiment':<30}  {'damage_end':>10}  {'max_km/h':>8}")
    print("  " + "-" * 110)

    seen_runs = set()
    for row in summary_rows:
        r = row.get("run_id", "")
        ep = row.get("episode_id", "")
        lap = row.get("lap_id", "")
        exp = row.get("experiment_id", row.get("experiment", ""))[:30]
        status = row.get("status", "")
        dmg_e = _fmt(row.get("damage_end", ""), ".0f")
        spd = _fmt(row.get("max_speed", ""), ".1f")
        seen_runs.add(r)
        print(f"  {r:<35} {ep:<16} {lap:>3}  {status:<12}  {exp:<30}  "
              f"{dmg_e:>10}  {spd:>8}")

    print(f"\n  {len(summary_rows)} lap(s) in summary ({len(seen_runs)} unique run(s)).")
    print("\nTo analyse a lap:")
    print("  python3 find_corners.py --run RUN_ID --episode EPISODE_ID --lap LAP_ID\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Identify corner/straight zones from gym_torcs lap telemetry.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples (Mac):\n"
            "  python3 find_corners.py --list\n"
            "  python3 find_corners.py --run 20261009_173451Z_e16440e5 "
            "--episode ep_734ba673 --lap 1\n"
            "  python3 find_corners.py --run 20261009_173451Z_e16440e5\n"
            "\n"
            "Threshold flags:\n"
            "  --corner-thresh METRES   (default 40)\n"
            "  --straight-thresh METRES (default 150)\n"
        ),
    )
    parser.add_argument("--run",       metavar="RUN_ID",     help="run_id to analyse")
    parser.add_argument("--episode",   metavar="EPISODE_ID", help="episode_id to analyse")
    parser.add_argument("--lap",       metavar="LAP_ID",     type=int, help="lap_id (integer)")
    parser.add_argument("--list",      action="store_true",  help="list available laps and exit")
    parser.add_argument("--data",      default="lap_data.csv",    metavar="FILE",
                        help="path to lap_data.csv (default: lap_data.csv)")
    parser.add_argument("--summary",   default="lap_summary.csv", metavar="FILE",
                        help="path to lap_summary.csv (default: lap_summary.csv)")
    parser.add_argument("--corner-thresh",   type=float, default=40.0,
                        metavar="M",
                        help="forward_track threshold for corner zones (default 40 m)")
    parser.add_argument("--straight-thresh", type=float, default=150.0,
                        metavar="M",
                        help="forward_track threshold for straight zones (default 150 m)")
    args = parser.parse_args()

    # Apply threshold overrides to module-level constants used by zone detection
    global CORNER_THRESH, STRAIGHT_THRESH
    CORNER_THRESH   = args.corner_thresh
    STRAIGHT_THRESH = args.straight_thresh

    # Load summary
    summary_rows = load_summary(args.summary)

    if args.list or (not args.run and not args.episode and args.lap is None):
        list_available(summary_rows, args.data)
        sys.exit(0)

    # --- Resolve run/episode/lap from arguments + summary ---

    # Filter summary rows to matching run
    if args.run:
        matching_runs = [r for r in summary_rows if r["run_id"] == args.run]
        if not matching_runs:
            print(f"\nERROR: run_id '{args.run}' not found in lap_summary.csv.")
            print("Available run IDs:")
            for r in sorted({row["run_id"] for row in summary_rows}):
                print(f"  {r}")
            sys.exit(1)
    else:
        matching_runs = summary_rows

    if args.episode:
        matching_runs = [r for r in matching_runs if r["episode_id"] == args.episode]
        if not matching_runs:
            print(f"\nERROR: episode_id '{args.episode}' not found "
                  f"(within run '{args.run}' if specified).")
            sys.exit(1)

    if args.lap is not None:
        matching_runs = [r for r in matching_runs if r["lap_id"] == str(args.lap)]
        if not matching_runs:
            print(f"\nERROR: lap_id '{args.lap}' not found "
                  f"(within the specified run/episode).")
            sys.exit(1)

    # Refuse to silently combine multiple laps
    if len(matching_runs) > 1:
        print(
            f"\nERROR: {len(matching_runs)} laps match the given filters. "
            "Specify --run, --episode and --lap to select exactly one.\n"
        )
        print(f"  {'run_id':<35} {'episode_id':<16} {'lap':>3}  {'status'}")
        print("  " + "-" * 70)
        for r in matching_runs:
            print(f"  {r['run_id']:<35} {r['episode_id']:<16} "
                  f"{r['lap_id']:>3}  {r.get('status','')}")
        print()
        sys.exit(1)

    summary_row = matching_runs[0]
    run_id     = summary_row["run_id"]
    episode_id = summary_row["episode_id"]
    lap_id     = int(summary_row["lap_id"])

    # --- Load data rows ---
    print(f"\nLoading lap_data.csv for run={run_id} episode={episode_id} lap={lap_id} …",
          end="", flush=True)
    rows, warnings = load_data_for_lap(args.data, run_id, episode_id, lap_id)
    print(f" {len(rows):,} rows loaded.")

    if not rows:
        print(
            f"\nERROR: No rows found in lap_data.csv matching "
            f"run={run_id}, episode={episode_id}, lap={lap_id}.\n"
            "The summary row exists but the data rows may have been trimmed."
        )
        sys.exit(1)

    # --- Header ---
    print()
    print("=" * 70)
    print("  gym_torcs — Corner / Straight Zone Analysis")
    print("=" * 70)
    print(f"  Run ID      : {run_id}")
    print(f"  Episode     : {episode_id}")
    print(f"  Lap ID      : {lap_id}")
    print(f"  Experiment  : {summary_row.get('experiment_id', summary_row.get('experiment', '—'))}")
    print(f"  Lap status  : {_lap_status_label(summary_row.get('status',''), summary_row.get('damage_start',''), summary_row.get('damage_end',''), summary_row.get('lap_time',''))}")
    print(f"  Max speed   : {_fmt(summary_row.get('max_speed',''), '.1f')} km/h")
    print(f"  Completion  : {summary_row.get('completion_reason','—')}")
    print(f"  Data rows   : {len(rows):,}")
    print()
    print(f"  Corner threshold   : forward_track < {CORNER_THRESH:.0f} m")
    print(f"  Straight threshold : forward_track > {STRAIGHT_THRESH:.0f} m")
    print(f"  Min zone samples   : {MIN_ZONE_SAMPLES}")
    print()
    print("  NOTE: forward_track is the single dead-ahead sensor (0°).")
    print("  It does NOT measure lateral track width or safe cornering radius.")
    print("  min_valid_track is the minimum of all 19 sensor readings and gives")
    print("  a rough indication of total clearance but is not sideways clearance.")

    # --- Sensor coverage summary ---
    total = len(rows)
    valid_fwd  = sum(1 for r in rows if _is_valid_forward_track(r["forward_track"]))
    blank_fwd  = sum(1 for r in rows if r["forward_track"] == "")
    invalid_fwd = total - valid_fwd - blank_fwd
    corner_samples  = sum(1 for r in rows if _zone_type(r["forward_track"]) == "corner")
    straight_samples = sum(1 for r in rows if _zone_type(r["forward_track"]) == "straight")
    mid_samples     = sum(1 for r in rows if _zone_type(r["forward_track"]) == "mid")

    print()
    print("─" * 70)
    print("  SENSOR COVERAGE")
    print("─" * 70)
    print(f"  Total steps              : {total:,}")
    print(f"  Valid forward_track      : {valid_fwd:,}  ({100*valid_fwd/total:.1f}%)")
    print(f"  Blank forward_track      : {blank_fwd:,}  ({100*blank_fwd/total:.1f}%)  "
          "← sensor off-road or pointing at wall — expected")
    if invalid_fwd:
        print(f"  Invalid forward_track    : {invalid_fwd:,}  ← non-finite / non-numeric values")
    print(f"  Corner-range samples     : {corner_samples:,}  (fwd < {CORNER_THRESH:.0f} m)")
    print(f"  Mid-range samples        : {mid_samples:,}  ({CORNER_THRESH:.0f}–{STRAIGHT_THRESH:.0f} m)")
    print(f"  Straight-range samples   : {straight_samples:,}  (fwd > {STRAIGHT_THRESH:.0f} m)")

    # recovery / reverse steps
    reverse_steps = sum(1 for r in rows if r.get("gear") == "-1")
    if reverse_steps:
        print(f"  Recovery (gear=-1) steps : {reverse_steps:,}  ← car in reverse / unstick mode")

    # --- Validation warnings ---
    if warnings:
        print()
        print("─" * 70)
        print(f"  VALIDATION WARNINGS ({len(warnings)})")
        print("─" * 70)
        for w in warnings[:20]:
            print(w)
        if len(warnings) > 20:
            print(f"  … {len(warnings) - 20} more warnings omitted.")

    # --- Lap status breakdown by lap_status column ---
    status_counts = defaultdict(int)
    for r in rows:
        status_counts[r.get("lap_status", "")] += 1
    if len(status_counts) > 1 or "" in status_counts:
        print()
        print("─" * 70)
        print("  LAP-STATUS BREAKDOWN (per-row lap_status field)")
        print("─" * 70)
        labels = {
            "warmup":   "warmup  — before first finish-line crossing",
            "partial":  "partial — lap started, finish line not yet crossed",
            "flying":   "flying  — full lap in progress after first crossing",
            "":         "(blank) — status field missing or empty",
        }
        for s, count in sorted(status_counts.items(), key=lambda x: -x[1]):
            label = labels.get(s, s)
            print(f"  {count:>7,}  {label}")

    # --- Distance range ---
    dists = [_to_float(r["distFromStart"]) for r in rows]
    dists = [d for d in dists if d is not None]
    dist_r_vals = [_to_float(r["distRaced"]) for r in rows]
    dist_r_vals = [d for d in dist_r_vals if d is not None]
    if dists:
        print()
        print("─" * 70)
        print("  DISTANCE RANGE")
        print("─" * 70)
        print(f"  distFromStart  : {min(dists):.1f} – {max(dists):.1f} m")
        if dist_r_vals:
            print(f"  distRaced      : {min(dist_r_vals):.1f} – {max(dist_r_vals):.1f} m "
                  f"(total covered: {max(dist_r_vals) - min(dist_r_vals):.1f} m)")

    # --- Damage timeline ---
    dmg_rows = [(r["distFromStart"], _to_float(r["damage"])) for r in rows
                if _to_float(r["damage"]) is not None]
    if dmg_rows:
        dmg_vals = [d for _, d in dmg_rows]
        dmg_start = dmg_vals[0]
        dmg_end   = dmg_vals[-1]
        if dmg_end > dmg_start:
            # find first step where damage increased
            first_dmg_step = None
            first_dmg_dist = None
            for r in rows:
                d = _to_float(r["damage"])
                if d is not None and d > dmg_start:
                    first_dmg_step = r.get("step")
                    first_dmg_dist = _to_float(r["distFromStart"])
                    break
            print()
            print("─" * 70)
            print("  DAMAGE TIMELINE")
            print("─" * 70)
            print(f"  Damage at lap start : {dmg_start:.0f} pts")
            print(f"  Damage at lap end   : {dmg_end:.0f} pts  (+{dmg_end - dmg_start:.0f} pts)")
            if first_dmg_dist is not None:
                print(f"  First increase at   : distFromStart ≈ {first_dmg_dist:.1f} m "
                      f"(step {first_dmg_step})")
        else:
            print()
            print("─" * 70)
            print(f"  DAMAGE: none accumulated during this lap (constant {dmg_end:.0f} pts).")

    # --- Zone detection ---
    corner_zones   = detect_zones(rows, "corner")
    straight_zones = detect_zones(rows, "straight")

    print(_zone_report(
        corner_zones, "corner",
        f"forward_track < {CORNER_THRESH:.0f} m"
    ))
    print(_zone_report(
        straight_zones, "straight",
        f"forward_track > {STRAIGHT_THRESH:.0f} m"
    ))

    # --- Summary counts ---
    print()
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Corner zones   found : {len(corner_zones)}")
    print(f"  Straight zones found : {len(straight_zones)}")
    print()
    print("  Reminder: thresholds are heuristic starting points.")
    print(f"  Adjust with --corner-thresh M and --straight-thresh M.")
    print("  forward_track < 40 m does not mean the car is in a hairpin;")
    print("  it means the dead-ahead ray hit a boundary within 40 m.")
    print("  Some corners appear as multiple short zones if the car oscillates")
    print("  around the threshold mid-corner.")
    print()


if __name__ == "__main__":
    main()
