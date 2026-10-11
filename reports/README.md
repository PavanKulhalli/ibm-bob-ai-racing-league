# TORCS Driving Bot — Experiment Reports

One `.txt` file per experiment run, named `report_<exp-tag>_<timestamp>.txt`.

Generated automatically by running:

    python3 find_corners.py --save
    python3 find_corners.py --exp exp-19 --save

Each report contains:
- Lap summary table (lap time, top speed, damage per lap)
- Braking zones (where the car brakes, entry speed, minimum speed reached)
- Tight corners (where ahead < 30 m — high-risk points)
- Damage events (exact track position and speed when damage occurred)
- Speed profile (20-sector heatmap of min/avg/max speed around the lap)
- Suggested next experiment (heuristic based on what the data shows)
