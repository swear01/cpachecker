#!/usr/bin/env python3
"""Validate and analyze VGuide predicate study dumps (see PREDICATE_ANALYSIS_PLAN.md).

Usage:
  python3 analyze_predicate_study.py --validate-only \\
    --dump-dir output/vguide/analysis_dumps/full_scalar_noL3_20260608 \\
    --logs-dir output/vguide/experiments/full_scalar_vguide_noL3_analysis/logs

  python3 analyze_predicate_study.py \\
    --dump-dir output/vguide/analysis_dumps/full_scalar_noL3_20260608 \\
    --logs-dir output/vguide/experiments/full_scalar_vguide_noL3_analysis/logs \\
    --stock-logs output/vguide/experiments/full_scalar_stock/logs \\
    --out output/vguide/analysis_dumps/full_scalar_noL3_20260608/analysis
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from z3_overlap import compute_overlap_z3  # noqa: E402

RE_LLM_ROUND = re.compile(r"VGuide LLM round #\d+")
RE_REPAIR = re.compile(r"ensemble L1 empty; one repair LLM call")
RE_VER = re.compile(r"Verification result:\s*(\w+)", re.I)
RE_WALL = re.compile(r"Total time for CPAchecker:\s+([\d.]+)")
RE_REFS = re.compile(r"Number of predicate refinements:\s+(\d+)")


@dataclass
class CheckFailure:
    task: str
    check: str
    message: str


@dataclass
class ValidationReport:
    failures: list[CheckFailure] = field(default_factory=list)
    tasks_checked: int = 0
    warnings: list[CheckFailure] = field(default_factory=list)

    def fail(self, task: str, check: str, message: str) -> None:
        self.failures.append(CheckFailure(task, check, message))

    def warn(self, task: str, check: str, message: str) -> None:
        self.warnings.append(CheckFailure(task, check, message))

    @property
    def ok(self) -> bool:
        return not self.failures


def load_manifest(path: Path) -> list[str]:
    tasks: list[str] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tasks.append(Path(line).stem)
    return tasks


def load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def norm_smt(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


_SSA_SUFFIX = re.compile(r"@\d+")


def canonicalize_smt(s: str) -> str:
    """Normalize SSA indices and internal .def_N names for dump cross-checks."""
    s = norm_smt(s)
    s = re.sub(r"\|([^|]+)@\d+\|", r"|\1|", s)
    s = re.sub(r"\b([A-Za-z_][\w:]*)@\d+\b", r"\1", s)
    s = re.sub(r"\.def_\d+", ".def_*", s)
    return s


def assert_part(s: str) -> str:
    m = re.search(r"\(assert\b", s or "")
    return canonicalize_smt(s[m.start() :] if m else s)


def load_log_verdict(log_path: Path) -> dict:
    if not log_path.is_file():
        return {}
    text = log_path.read_text(errors="replace")
    m = RE_VER.search(text)
    verdict = m.group(1).upper() if m else "UNKNOWN"
    wm = RE_WALL.search(text)
    wall = float(wm.group(1)) if wm else 0.0
    rm = RE_REFS.search(text)
    refs = int(rm.group(1)) if rm else 0
    return {"verdict": verdict, "wall_s": wall, "refinements": refs}


def load_csv_verdicts(csv_path: Path) -> dict[str, dict]:
    if not csv_path.is_file():
        return {}
    out: dict[str, dict] = {}
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            out[row["task"]] = {
                "verdict": row.get("result", "UNKNOWN").upper(),
                "wall_s": float(row.get("wall_s") or 0),
                "refinements": int(row.get("refinements") or 0),
            }
    return out


def task_meta(
    task: str,
    task_dir: Path,
    analysis_logs: dict[str, dict],
    stock_logs: dict[str, dict],
) -> dict:
    summary = load_json(task_dir / "task_summary.json")
    if summary:
        return {
            "task": task,
            "verdict": summary.get("verdict", "UNKNOWN"),
            "wall_s": summary.get("wall_s", 0),
            "refinements_cpa": summary.get("refinements", 0),
            "spurious_refinements": len(load_jsonl(task_dir / "refinements.jsonl")),
            "llm_rounds": summary.get("llm_rounds", 0),
            "llm_api_calls": summary.get("llm_api_calls", 0),
            "vguide_outcome": summary.get("vguide_outcome", ""),
            "incomplete": False,
            "stock_verdict": stock_logs.get(task, {}).get("verdict", ""),
        }
    fb = analysis_logs.get(task, {})
    return {
        "task": task,
        "verdict": fb.get("verdict", "UNKNOWN"),
        "wall_s": fb.get("wall_s", 0),
        "refinements_cpa": fb.get("refinements", 0),
        "spurious_refinements": len(load_jsonl(task_dir / "refinements.jsonl")),
        "llm_rounds": len({r.get("llm_round_index") for r in load_jsonl(task_dir / "llm_rounds.jsonl")}),
        "llm_api_calls": len(load_jsonl(task_dir / "llm_rounds.jsonl")),
        "vguide_outcome": "",
        "incomplete": True,
        "stock_verdict": stock_logs.get(task, {}).get("verdict", ""),
    }


def predicate_in_local(local: dict, loop_head: str, smt: str, *, relaxed: bool = False) -> bool:
    """Check if predicate SMT appears at loop_head in a precision local snapshot."""
    preds = local.get(loop_head, [])
    if not isinstance(preds, list):
        return False
    if not relaxed:
        norm = norm_smt(smt)
        return any(norm_smt(p) == norm for p in preds)
    target = assert_part(smt)
    if not target:
        return False
    for p in preds:
        cand = assert_part(p)
        if cand == target or target in cand or cand in target:
            return True
    return False


def precision_injected_keys(ref: dict) -> set[tuple[str, str]]:
    return {
        (x.get("loop_head", ""), norm_smt(x.get("smt_dump", "")))
        for x in ref.get("precision_injected", [])
    }


def vp_in_precision_injected(ref: dict, vp: dict) -> bool:
    key = (vp.get("loop_head", ""), norm_smt(vp.get("smt_dump", "")))
    return key in precision_injected_keys(ref)


def in_final_precision(precision_final: dict, loop_head: str, smt: str) -> bool:
    if not precision_final:
        return False
    local = precision_final.get("local", {})
    if predicate_in_local(local, loop_head, smt):
        return True
    global_preds = precision_final.get("global", [])
    ns = norm_smt(smt)
    return any(norm_smt(g) == ns for g in global_preds)


def validate_task(
    task: str,
    dump_root: Path,
    log_path: Path | None,
    dump_prompts: bool,
    report: ValidationReport,
) -> None:
    report.tasks_checked += 1
    task_dir = dump_root / "tasks" / task

    summary_path = task_dir / "task_summary.json"
    summary = load_json(summary_path)
    if summary is None:
        report.warn(task, "V2", f"missing task_summary.json (INCOMPLETE hang?)")
        if not log_path or not log_path.is_file():
            report.fail(task, "V2", "no task_summary and no log")
            return
    elif not summary.get("verdict"):
        report.fail(task, "V2", "task_summary.json missing verdict")

    refinements = load_jsonl(task_dir / "refinements.jsonl")
    llm_rounds = load_jsonl(task_dir / "llm_rounds.jsonl")
    spurious_count = len(refinements)
    ref_count = int(summary.get("refinements", 0)) if summary else spurious_count

    if ref_count == 0:
        if refinements:
            report.fail(task, "V3", f"expected 0 refinements.jsonl lines, got {spurious_count}")
    elif spurious_count not in (ref_count, ref_count - 1):
        report.warn(
            task,
            "V3",
            f"spurious lines {spurious_count} vs cpa refs {ref_count} (expected equal or cpa-1)",
        )

    if summary and "precision_final" not in summary:
        report.fail(task, "V8", "task_summary missing precision_final")

    log_text = log_path.read_text(errors="replace") if log_path and log_path.is_file() else ""
    llm_api_calls = int(summary.get("llm_api_calls", 0)) if summary else len(llm_rounds)

    if RE_LLM_ROUND.search(log_text):
        if llm_api_calls <= 0 and llm_rounds:
            report.fail(task, "V4", "log has VGuide LLM round but llm_api_calls=0")
        for row in llm_rounds:
            usage = row.get("usage")
            if not usage or int(usage.get("prompt_tokens", 0)) <= 0:
                report.fail(
                    task,
                    "V4",
                    f"llm_rounds api_call_index={row.get('api_call_index')} missing usage.prompt_tokens",
                )
    if RE_REPAIR.search(log_text):
        if not any(r.get("call_kind") == "repair" for r in llm_rounds):
            report.fail(task, "V9", "log mentions repair LLM call but no call_kind=repair in llm_rounds")

    for row in refinements:
        idx = row.get("refinement_index")
        llm_called = bool(row.get("llm_called"))
        if not llm_called:
            if not row.get("llm_skip_reason"):
                report.fail(task, "V5", f"refinement {idx} llm_called=false but no llm_skip_reason")
        else:
            itps = row.get("interpolants_pre", [])
            if not itps:
                report.fail(task, "V6", f"refinement {idx} llm_called but interpolants_pre empty")
            if "validated_predicates" not in row:
                report.fail(task, "V6", f"refinement {idx} missing validated_predicates")

            local_after = row.get("precision_local_after", {})
            for vp in row.get("validated_predicates", []):
                if not vp.get("injected"):
                    continue
                head = vp.get("loop_head", "")
                smt = vp.get("smt_dump", "")
                if not vp_in_precision_injected(row, vp):
                    report.fail(
                        task,
                        "V7",
                        f"refinement {idx} injected predicate {vp.get('predicate_id')} missing from precision_injected",
                    )
                    continue
                if not predicate_in_local(local_after, head, smt, relaxed=True):
                    report.warn(
                        task,
                        "V7",
                        f"refinement {idx} predicate {vp.get('predicate_id')} in precision_injected but "
                        "SMT string differs from precision_local_after (SSA/.def canonicalization)",
                    )

    if dump_prompts:
        for row in llm_rounds:
            rel = row.get("prompt_path")
            if not rel:
                report.fail(
                    task,
                    "V10",
                    f"api_call_index={row.get('api_call_index')} missing prompt_path",
                )
                continue
            if not (task_dir / rel).is_file():
                report.fail(task, "V10", f"missing prompt file {rel}")


def validate_dump(
    dump_dir: Path,
    manifest: Path,
    logs_dir: Path | None,
    expected_count: int | None,
) -> ValidationReport:
    report = ValidationReport()
    tasks = load_manifest(manifest)
    if expected_count is not None and len(tasks) != expected_count:
        report.fail("-", "V1", f"manifest has {len(tasks)} tasks, expected {expected_count}")

    manifest_json = load_json(dump_dir / "run_manifest.json") or {}
    dump_prompts = bool(manifest_json.get("dump_prompts", False))

    tasks_root = dump_dir / "tasks"
    if not tasks_root.is_dir():
        report.fail("-", "V1", f"tasks/ missing under {dump_dir}")
        return report

    present = {p.name for p in tasks_root.iterdir() if p.is_dir()}
    for task in tasks:
        if task not in present:
            report.fail(task, "V1", "task directory missing")

    for task in sorted(present - set(tasks)):
        report.fail(task, "V1", "unexpected task directory (not in manifest)")

    for task in tasks:
        log_path = logs_dir / f"{task}.log" if logs_dir else None
        validate_task(task, dump_dir, log_path, dump_prompts, report)

    return report


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def run_analysis(
    dump_dir: Path,
    manifest: Path,
    logs_dir: Path | None,
    stock_logs_dir: Path | None,
    out_dir: Path,
    z3_timeout_ms: int = 8000,
) -> None:
    tasks = load_manifest(manifest)
    tasks_root = dump_dir / "tasks"
    out_dir.mkdir(parents=True, exist_ok=True)

    analysis_csv = {}
    if logs_dir:
        csv_path = logs_dir.parent / f"{manifest.stem}_summary.csv"
        if not csv_path.is_file():
            csv_path = logs_dir.parent / "full_scalar_summary.csv"
        analysis_csv = load_csv_verdicts(csv_path)

    stock_csv = {}
    if stock_logs_dir:
        sp = stock_logs_dir.parent / "full_scalar_summary.csv"
        stock_csv = load_csv_verdicts(sp)

    # --- context_budget.csv ---
    budget_rows: list[dict] = []
    for task in tasks:
        for row in load_jsonl(tasks_root / task / "llm_rounds.jsonl"):
            usage = row.get("usage") or {}
            details_p = usage.get("prompt_tokens_details") or {}
            details_c = usage.get("completion_tokens_details") or {}
            comps = row.get("prompt_components") or {}
            budget_rows.append(
                {
                    "task": task,
                    "refinement_index": row.get("refinement_index"),
                    "llm_round_index": row.get("llm_round_index"),
                    "api_call_index": row.get("api_call_index"),
                    "call_kind": row.get("call_kind"),
                    "prompt_kind": row.get("prompt_kind"),
                    "prompt_tokens": usage.get("prompt_tokens", 0),
                    "completion_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                    "prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens", 0),
                    "prompt_cache_miss_tokens": usage.get("prompt_cache_miss_tokens", 0),
                    "reasoning_tokens": details_c.get("reasoning_tokens", 0),
                    "latency_ms": row.get("latency_ms", 0),
                    "prompt_chars": row.get("prompt_chars", 0),
                    "chars_source": comps.get("source", 0),
                    "chars_contract": comps.get("contract", 0),
                    "chars_trace": comps.get("trace", 0),
                    "chars_rules": comps.get("rules", 0),
                    "chars_loop_heads": comps.get("loop_heads", 0),
                }
            )
    write_csv(
        out_dir / "context_budget.csv",
        [
            "task",
            "refinement_index",
            "llm_round_index",
            "api_call_index",
            "call_kind",
            "prompt_kind",
            "prompt_tokens",
            "completion_tokens",
            "total_tokens",
            "prompt_cache_hit_tokens",
            "prompt_cache_miss_tokens",
            "reasoning_tokens",
            "latency_ms",
            "prompt_chars",
            "chars_source",
            "chars_contract",
            "chars_trace",
            "chars_rules",
            "chars_loop_heads",
        ],
        budget_rows,
    )

    budget_task_rows: list[dict] = []
    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in budget_rows:
        by_task[r["task"]].append(r)
    for task in tasks:
        rows = by_task.get(task, [])
        meta = task_meta(task, tasks_root / task, analysis_csv, stock_csv)
        budget_task_rows.append(
            {
                **meta,
                "api_calls": len(rows),
                "prompt_tokens_sum": sum(int(r["prompt_tokens"]) for r in rows),
                "completion_tokens_sum": sum(int(r["completion_tokens"]) for r in rows),
                "total_tokens_sum": sum(int(r["total_tokens"]) for r in rows),
                "latency_ms_sum": sum(int(r["latency_ms"]) for r in rows),
                "prompt_tokens_median": sorted(int(r["prompt_tokens"]) for r in rows)[
                    len(rows) // 2
                ]
                if rows
                else 0,
            }
        )
    write_csv(
        out_dir / "context_budget_per_task.csv",
        [
            "task",
            "verdict",
            "stock_verdict",
            "incomplete",
            "wall_s",
            "refinements_cpa",
            "spurious_refinements",
            "llm_rounds",
            "llm_api_calls",
            "api_calls",
            "prompt_tokens_sum",
            "completion_tokens_sum",
            "total_tokens_sum",
            "prompt_tokens_median",
            "latency_ms_sum",
            "vguide_outcome",
        ],
        budget_task_rows,
    )

    # --- pcs / overlap per predicate ---
    pcs_rows: list[dict] = []
    overlap_class_counts: Counter[str] = Counter()
    tasks_with_llm = 0
    preds_total = 0
    preds_injected = 0

    for task in tasks:
        task_dir = tasks_root / task
        meta = task_meta(task, task_dir, analysis_csv, stock_csv)
        precision_final = (load_json(task_dir / "task_summary.json") or {}).get(
            "precision_final", {}
        )
        solved = meta["verdict"] in ("TRUE", "FALSE")
        had_llm = False

        for ref in load_jsonl(task_dir / "refinements.jsonl"):
            if not ref.get("llm_called"):
                continue
            had_llm = True
            interpolants = ref.get("interpolants_pre", [])
            prec_before = ref.get("precision_local_before", {})

            injected_set = precision_injected_keys(ref)
            local_after = ref.get("precision_local_after", {})

            for vp in ref.get("validated_predicates", []):
                preds_total += 1
                smt = vp.get("smt_dump", "")
                loop_head = vp.get("loop_head", "")
                injected = bool(vp.get("injected")) or (
                    loop_head,
                    norm_smt(smt),
                ) in injected_set or predicate_in_local(local_after, loop_head, smt, relaxed=True)
                if injected:
                    preds_injected += 1

                block_smt = vp.get("block_formula_smt", "") or ""
                o_class, r_i, r_t, r_p, n_score, z3_st = compute_overlap_z3(
                    smt,
                    loop_head,
                    interpolants,
                    prec_before,
                    block_smt,
                    timeout_ms=z3_timeout_ms,
                )
                overlap_class_counts[o_class] += 1
                pcs_rows.append(
                    {
                        "task": task,
                        "verdict": meta["verdict"],
                        "stock_verdict": meta["stock_verdict"],
                        "refinement_index": ref.get("refinement_index"),
                        "predicate_id": vp.get("predicate_id"),
                        "loop_head": loop_head,
                        "raw_string": vp.get("raw_string", ""),
                        "classification": vp.get("classification", ""),
                        "injected": injected,
                        "overlap_class": o_class,
                        "R_I": round(r_i, 3),
                        "R_T": round(r_t, 3),
                        "R_P": round(r_p, 3),
                        "N": round(n_score, 3),
                        "R_I_status": z3_st["R_I"],
                        "R_P_status": z3_st["R_P"],
                        "R_T_status": z3_st["R_T"],
                        "in_final_precision": in_final_precision(precision_final, loop_head, smt),
                        "task_solved": solved,
                        "pcs_mode": "z3",
                    }
                )

        if had_llm:
            tasks_with_llm += 1

    write_csv(
        out_dir / "pcs_per_predicate.csv",
        [
            "task",
            "verdict",
            "stock_verdict",
            "refinement_index",
            "predicate_id",
            "loop_head",
            "raw_string",
            "classification",
            "injected",
            "overlap_class",
            "R_I",
            "R_T",
            "R_P",
            "N",
            "R_I_status",
            "R_P_status",
            "R_T_status",
            "in_final_precision",
            "task_solved",
            "pcs_mode",
        ],
        pcs_rows,
    )

    # --- overlap_summary.csv (per task) ---
    overlap_task: dict[str, Counter] = defaultdict(Counter)
    for row in pcs_rows:
        overlap_task[row["task"]][row["overlap_class"]] += 1

    overlap_summary_rows: list[dict] = []
    for task in tasks:
        meta = task_meta(task, tasks_root / task, analysis_csv, stock_csv)
        oc = overlap_task.get(task, Counter())
        total_p = sum(oc.values())
        overlap_summary_rows.append(
            {
                "task": task,
                "verdict": meta["verdict"],
                "stock_verdict": meta["stock_verdict"],
                "llm_predicates": total_p,
                "redundant": oc.get("Redundant", 0),
                "novel": oc.get("Novel", 0),
                "orthogonal": oc.get("Orthogonal", 0),
                "vacuous": oc.get("Vacuous", 0),
                "pct_novel": round(100.0 * oc.get("Novel", 0) / total_p, 1) if total_p else 0,
            }
        )
    write_csv(
        out_dir / "overlap_summary.csv",
        [
            "task",
            "verdict",
            "stock_verdict",
            "llm_predicates",
            "redundant",
            "novel",
            "orthogonal",
            "vacuous",
            "pct_novel",
        ],
        overlap_summary_rows,
    )

    # --- analysis_report.md ---
    prompt_tokens = [int(r["prompt_tokens"]) for r in budget_rows if int(r["prompt_tokens"]) > 0]
    pt_sorted = sorted(prompt_tokens)
    verdict_counts = Counter(m["verdict"] for m in budget_task_rows)
    stock_rescued = sum(
        1
        for m in budget_task_rows
        if m["stock_verdict"] == "UNKNOWN" and m["verdict"] in ("TRUE", "FALSE")
    )

    report_lines = [
        "# VGuide Predicate Study — Phase D (Z3 overlap / PCS)",
        "",
        f"Dump: `{dump_dir}`",
        f"Tasks: {len(tasks)}",
        "",
        "## Headline",
        "",
        f"- Verdicts: {dict(verdict_counts)}",
        f"- Tasks with ≥1 LLM round (validated predicates): {tasks_with_llm}",
        f"- Total validated LLM predicates: {preds_total} (injected {preds_injected})",
        f"- Stock UNKNOWN → solved (TRUE/FALSE): {stock_rescued}",
        "",
        "## Context budget (API usage)",
        "",
    ]
    if pt_sorted:
        report_lines += [
            f"- API calls: {len(prompt_tokens)}",
            f"- prompt_tokens per call: min={pt_sorted[0]}, median={pt_sorted[len(pt_sorted)//2]}, max={pt_sorted[-1]}",
            f"- total prompt_tokens: {sum(prompt_tokens)}",
            "",
        ]
    report_lines += [
        "## Overlap class (Z3 entailment, all validated predicates)",
        "",
        f"- {dict(overlap_class_counts)}",
        "",
        "## Notes",
        "",
        "- Overlap via Z3: R_I=I⊨q, R_P=P_loc⊨q (same SSA only), R_T=block⊨q; see OVERLAP_AND_PCS.md.",
        "- V3 off-by-one (cpa refinements vs spurious jsonl) is expected when last refinement is feasible CE.",
        "- All 217 tasks should have `task_summary.json` after 2026-06-08 hang rerun + dumper shutdown hook.",
        "",
        "## Outputs",
        "",
        "- `context_budget.csv` — per API call",
        "- `context_budget_per_task.csv` — per task rollup",
        "- `pcs_per_predicate.csv` — per predicate Z3 overlap / PCS",
        "- `overlap_summary.csv` — per task overlap counts",
        "",
    ]
    (out_dir / "analysis_report.md").write_text("\n".join(report_lines))

    print(f"Wrote analysis to {out_dir}")
    print(f"  context_budget.csv: {len(budget_rows)} API calls")
    print(f"  pcs_per_predicate.csv: {len(pcs_rows)} predicates")
    print(f"  tasks with LLM predicates: {tasks_with_llm}")


def main() -> int:
    ap = argparse.ArgumentParser(description="VGuide predicate study dump validation / analysis")
    ap.add_argument("--dump-dir", type=Path, required=True)
    ap.add_argument(
        "--manifest",
        type=Path,
        default=Path("docs/vguided-cegar/benchmark_sets/full_scalar.list"),
    )
    ap.add_argument("--logs-dir", type=Path, default=None)
    ap.add_argument("--stock-logs", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--expected-tasks", type=int, default=217)
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--skip-validate", action="store_true")
    ap.add_argument("--z3-timeout-ms", type=int, default=8000, help="Z3 per-query timeout")
    args = ap.parse_args()

    out_dir = args.out or (args.dump_dir / "analysis")

    if not args.skip_validate:
        report = validate_dump(args.dump_dir, args.manifest, args.logs_dir, args.expected_tasks)
        if report.warnings:
            print(f"WARNINGS: {len(report.warnings)} (non-fatal)")
            for w in report.warnings[:10]:
                print(f"  [{w.check}] {w.task}: {w.message}")
        if args.validate_only:
            if report.ok:
                print(f"OK: {report.tasks_checked} tasks passed (warnings={len(report.warnings)})")
                return 0
            print(f"FAILED: {len(report.failures)} issue(s) across {report.tasks_checked} tasks")
            for f in report.failures[:50]:
                print(f"  [{f.check}] {f.task}: {f.message}")
            if len(report.failures) > 50:
                print(f"  ... and {len(report.failures) - 50} more")
            return 1

    if args.validate_only:
        return 0

    run_analysis(
        args.dump_dir,
        args.manifest,
        args.logs_dir,
        args.stock_logs,
        out_dir,
        z3_timeout_ms=args.z3_timeout_ms,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
