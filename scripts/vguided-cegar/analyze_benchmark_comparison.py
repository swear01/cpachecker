#!/usr/bin/env python3
"""Compare VGuide vs baseline: PAR-2, solved counts, cactus plot, pairwise time.

PAR-2 (SV-COMP style): per task, score = wall_s if TRUE/FALSE else 2 * timelimit.
Cactus: cumulative # solved (TRUE+FALSE) vs time threshold.

Usage:
  python3 analyze_benchmark_comparison.py \\
    --vguide-logs output/vguide/experiments/full_scalar_vguide/logs \\
    --baseline-logs output/vguide/experiments/full_scalar_stock/logs \\
    --manifest docs/vguided-cegar/benchmark_sets/full_scalar.list \\
    --timelimit 300 \\
    --out output/vguide/experiments/full_scalar_vguide
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

RE_VER = re.compile(r"Verification result:\s*(\w+)", re.I)
RE_WALL = re.compile(r"Total time for CPAchecker:\s+([\d.]+)")
RE_REFS = re.compile(r"Number of predicate refinements:\s+(\d+)")


@dataclass
class TaskRun:
    task: str
    result: str
    wall_s: float
    refs: int

    @property
    def solved(self) -> bool:
        return self.result in ("TRUE", "FALSE")

    def par2(self, timelimit: float) -> float:
        return self.wall_s if self.solved else 2.0 * timelimit


def load_manifest(path: Path) -> list[str]:
    tasks = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tasks.append(Path(line).stem)
    return tasks


def parse_log(path: Path) -> TaskRun | None:
    if not path.is_file():
        return None
    text = path.read_text(errors="replace")
    m = RE_VER.search(text)
    if m:
        result = m.group(1).upper()
    elif "Exception" in text or "java.lang." in text:
        result = "ERROR"
    else:
        result = "UNKNOWN"
    wm = RE_WALL.search(text)
    wall = float(wm.group(1)) if wm else 0.0
    rm = RE_REFS.search(text)
    refs = int(rm.group(1)) if rm else 0
    return TaskRun(task="", result=result, wall_s=wall, refs=refs)


def cactus_curve(runs: dict[str, TaskRun], timelimit: float) -> list[tuple[float, int]]:
    """(time_threshold, cumulative_solved) including penalty point at 2*T."""
    solved_times = sorted(r.wall_s for r in runs.values() if r.solved)
    unsolved = sum(1 for r in runs.values() if not r.solved)
    points: list[tuple[float, int]] = [(0.0, 0)]
    cum = 0
    for t in solved_times:
        cum += 1
        points.append((t, cum))
    if unsolved:
        points.append((2.0 * timelimit, cum + unsolved))
    return points


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--vguide-logs", type=Path, required=True)
    ap.add_argument("--baseline-logs", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--timelimit", type=float, default=300.0)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--baseline-name", default="stock")
    ap.add_argument("--vguide-name", default="vguide")
    args = ap.parse_args()

    tasks = load_manifest(args.manifest)
    base: dict[str, TaskRun] = {}
    vg: dict[str, TaskRun] = {}
    for task in tasks:
        br = parse_log(args.baseline_logs / f"{task}.log")
        vr = parse_log(args.vguide_logs / f"{task}.log")
        if br:
            br.task = task
            base[task] = br
        if vr:
            vr.task = task
            vg[task] = vr

    common = sorted(set(base) & set(vg))
    n = len(common)
    if n == 0:
        raise SystemExit("No overlapping tasks with logs")

    args.out.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []

    def emit(s: str = "") -> None:
        lines.append(s)
        print(s)

    emit(f"Tasks compared: {n} / {len(tasks)} manifest")
    emit(f"Timelimit: {args.timelimit}s  |  PAR-2 penalty for unsolved: {2*args.timelimit}s")
    emit()

    for name, runs in ((args.baseline_name, base), (args.vguide_name, vg)):
        subset = {t: runs[t] for t in common}
        solved = [r for r in subset.values() if r.solved]
        par2_scores = [r.par2(args.timelimit) for r in subset.values()]
        par2_sum = sum(par2_scores)
        par2_avg = par2_sum / n
        emit(f"=== {name} ===")
        emit(
            f"  Solved (TRUE+FALSE): {len(solved)}/{n}  "
            f"(TRUE {sum(1 for r in solved if r.result=='TRUE')}, "
            f"FALSE {sum(1 for r in solved if r.result=='FALSE')})"
        )
        if solved:
            walls = [r.wall_s for r in solved]
            emit(
                f"  Wall time (solved only): min={min(walls):.2f}s  "
                f"median={sorted(walls)[len(walls)//2]:.2f}s  "
                f"mean={sum(walls)/len(walls):.2f}s  max={max(walls):.2f}s"
            )
        emit(f"  PAR-2 sum: {par2_sum:.1f}s  |  PAR-2 avg: {par2_avg:.2f}s")
        emit()

    b_par2 = {t: base[t].par2(args.timelimit) for t in common}
    v_par2 = {t: vg[t].par2(args.timelimit) for t in common}
    vg_wins_par2 = sum(1 for t in common if v_par2[t] < b_par2[t])
    base_wins_par2 = sum(1 for t in common if b_par2[t] < v_par2[t])
    par2_ties = n - vg_wins_par2 - base_wins_par2
    emit("=== PAR-2 per-task (lower is better) ===")
    emit(f"  VGuide lower: {vg_wins_par2}  |  Stock lower: {base_wins_par2}  |  Tie: {par2_ties}")
    emit(
        f"  Δ PAR-2 sum (stock − vguide): "
        f"{sum(b_par2[t] for t in common) - sum(v_par2[t] for t in common):.1f}s"
    )
    emit()

    both_solved = [
        t
        for t in common
        if base[t].solved and vg[t].solved and base[t].result == vg[t].result
    ]
    vg_faster = sum(1 for t in both_solved if vg[t].wall_s < base[t].wall_s - 0.01)
    base_faster = sum(1 for t in both_solved if base[t].wall_s < vg[t].wall_s - 0.01)
    emit(f"=== Wall time (both solved same verdict: {len(both_solved)} tasks) ===")
    emit(f"  VGuide faster: {vg_faster}  |  Stock faster: {base_faster}")
    if both_solved:
        ratios = [vg[t].wall_s / base[t].wall_s for t in both_solved if base[t].wall_s > 0]
        if ratios:
            emit(
                f"  VGuide/stock wall ratio (solved): median={sorted(ratios)[len(ratios)//2]:.2f}  "
                f"mean={sum(ratios)/len(ratios):.2f}"
            )
    emit()

    # Outcome buckets (from compare_official_reference)
    def bucket(r: str) -> str:
        if r == "TRUE":
            return "TRUE"
        if r == "FALSE":
            return "FALSE"
        return "INCOMPLETE"

    score = {"TRUE": 3, "FALSE": 2, "INCOMPLETE": 1}
    imp = deg = same = 0
    for t in common:
        bs, vs = score[bucket(base[t].result)], score[bucket(vg[t].result)]
        if vs > bs:
            imp += 1
        elif vs < bs:
            deg += 1
        else:
            same += 1
    emit("=== Verdict buckets (TRUE/FALSE/INCOMPLETE) ===")
    emit(f"  Improved: {imp}  |  Same: {same}  |  Degraded: {deg}")
    emit("  (Same = same bucket, not necessarily same wall time)")
    emit()

    # Cactus plot
    try:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(8, 5))
        for label, runs, color in (
            (args.baseline_name, base, "#4C72B0"),
            (args.vguide_name, vg, "#C44E52"),
        ):
            subset = {t: runs[t] for t in common}
            pts = cactus_curve(subset, args.timelimit)
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            ax.step(xs, ys, where="post", label=label, color=color, linewidth=2)
        ax.set_xscale("log")
        ax.set_xlabel("Time limit (s, log scale)")
        ax.set_ylabel("Cumulative solved (TRUE + FALSE)")
        ax.set_title(f"Cactus plot ({n} tasks, timelimit={args.timelimit:.0f}s)")
        ax.grid(True, alpha=0.3)
        ax.legend()
        ax.set_xlim(left=0.5)
        png = args.out / "cactus_vs_stock.png"
        fig.tight_layout()
        fig.savefig(png, dpi=150)
        plt.close(fig)
        emit(f"Wrote cactus plot: {png}")
    except ImportError:
        emit("(matplotlib not available — skipped cactus PNG)")

    report = args.out / "analysis_vs_stock.txt"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    emit(f"Wrote report: {report}")


if __name__ == "__main__":
    main()
