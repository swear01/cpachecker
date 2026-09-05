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
RE_VGUIDE_HOOK = re.compile(r"Unified VGuide CEGAR enabled")
RE_VGUIDE_EVENT = re.compile(r"VGuide (?:peel:|LLM round|analysis dump|outcome:)")
RE_PROVIDER_FAILURE = re.compile(r"VGuide LLM call failed")
RE_ANALYSIS_CRASH = re.compile(
    r"(?:SIG(?:SEGV|ABRT|BUS|ILL|FPE)|Segmentation fault|stack smashing detected|"
    r"A fatal error has been detected by the Java Runtime Environment|"
    r"Exception in thread\b|java\.lang\.[\w$]*(?:Exception|Error)\b|"
    r"\bNoSuch(?:Method|Field)Error\b|\bOutOfMemoryError\b|\bhs_err_pid\d+)"
)
SCHEDULE_SKIP_REASONS = {
    "schedule",
    "wall_budget",
    "process_round_cap",
    "source_prior",
}


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


@dataclass(frozen=True)
class Coverage:
    status: str
    reason: str
    dump_status: str
    evidence: tuple[str, ...] = ()

    def fields(self) -> dict[str, str]:
        return {
            "coverage_status": self.status,
            "coverage_reason": self.reason,
            "dump_status": self.dump_status,
            "coverage_evidence": ";".join(self.evidence),
        }


def load_manifest(path: Path) -> list[str]:
    tasks: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        tasks.append(Path(line).stem)
    return tasks


def load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def load_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if not isinstance(row, dict):
            raise TypeError("JSONL row is not an object")
        rows.append(row)
    return rows


def load_jsonl_state(path: Path) -> tuple[list[dict], str | None]:
    """Load JSONL while retaining missing/malformed-file evidence."""
    if not path.is_file():
        return [], "missing"
    try:
        return load_jsonl(path), None
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError):
        return [], "malformed"


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
    text = log_path.read_text(encoding="utf-8", errors="replace")
    m = RE_VER.search(text)
    verdict = m.group(1).upper() if m else "UNKNOWN"
    wm = RE_WALL.search(text)
    wall = float(wm.group(1)) if wm else None
    rm = RE_REFS.search(text)
    refs = int(rm.group(1)) if rm else None
    return {"verdict": verdict, "wall_s": wall, "refinements": refs}


def load_csv_verdicts(csv_path: Path) -> dict[str, dict]:
    if not csv_path.is_file():
        return {}
    out: dict[str, dict] = {}
    with csv_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["task"]] = {
                "verdict": row.get("result", "UNKNOWN").upper(),
                "wall_s": float(row["wall_s"]) if row.get("wall_s") else None,
                "refinements": int(row["refinements"]) if row.get("refinements") else None,
            }
    return out


def classify_coverage(task_dir: Path, log_text: str = "") -> Coverage:
    """Classify dump coverage without turning missing evidence into zeroes."""
    task_summary_path = task_dir / "task_summary.json"
    summary = load_json(task_summary_path)
    refinements, refinements_state = load_jsonl_state(task_dir / "refinements.jsonl")
    llm_rounds, llm_state = load_jsonl_state(task_dir / "llm_rounds.jsonl")
    provider_failure = bool(RE_PROVIDER_FAILURE.search(log_text)) or any(
        r.get("llm_skip_reason") == "llm_failed" for r in refinements
    )
    hook_reached = bool(
        RE_VGUIDE_HOOK.search(log_text)
        or RE_VGUIDE_EVENT.search(log_text)
        or provider_failure
    )
    evidence: list[str] = []
    if RE_VGUIDE_HOOK.search(log_text):
        evidence.append("hook_log")
    elif RE_VGUIDE_EVENT.search(log_text):
        evidence.append("vguide_event_log")

    if RE_ANALYSIS_CRASH.search(log_text):
        dump_status = "present" if task_dir.is_dir() else "missing"
        return Coverage("analysis_crash", "crash_evidence", dump_status, tuple(evidence + ["crash_log"]))

    if not task_dir.is_dir():
        if hook_reached:
            return Coverage("dump_incomplete", "missing_task_directory", "missing", tuple(evidence))
        if log_text and (RE_VER.search(log_text) or "Error:" in log_text):
            return Coverage("vguide_not_reached", "no_hook_evidence", "not_applicable", ("completed_log",))
        return Coverage("dump_incomplete", "missing_dump_evidence", "missing", ())

    if not task_summary_path.is_file():
        return Coverage("dump_incomplete", "missing_task_summary", "incomplete", tuple(evidence))
    if summary is None:
        return Coverage("dump_incomplete", "malformed_task_summary", "malformed", tuple(evidence))
    if refinements_state == "malformed" or llm_state == "malformed":
        return Coverage("dump_incomplete", "malformed_jsonl", "malformed", tuple(evidence))
    if provider_failure:
        return Coverage("provider_failure", "llm_failed", "present", tuple(evidence + ["provider_log"]))

    refinement_count = summary.get("refinements")
    if refinement_count is None:
        return Coverage("dump_incomplete", "missing_refinement_count", "incomplete", tuple(evidence))
    if not isinstance(refinement_count, int) or refinement_count < 0:
        return Coverage("dump_incomplete", "malformed_refinement_count", "malformed", tuple(evidence))
    if refinement_count > 0 and refinements_state == "missing":
        return Coverage("dump_incomplete", "missing_refinements_jsonl", "incomplete", tuple(evidence))
    llm_count = summary.get("llm_rounds")
    api_count = summary.get("llm_api_calls")
    if any(
        count is not None and (not isinstance(count, int) or count < 0)
        for count in (llm_count, api_count)
    ):
        return Coverage("dump_incomplete", "malformed_llm_count", "malformed", tuple(evidence))
    if any(count and count > 0 for count in (llm_count, api_count)) and llm_state == "missing":
        return Coverage("dump_incomplete", "missing_llm_rounds_jsonl", "incomplete", tuple(evidence))
    if refinement_count == 0 and not refinements:
        return Coverage(
            "no_spurious_ce",
            "zero_spurious_refinements",
            "present",
            tuple(evidence + ["summary"]),
        )

    skip_reasons = {r.get("llm_skip_reason") for r in refinements if not r.get("llm_called")}
    if not llm_rounds and skip_reasons & SCHEDULE_SKIP_REASONS:
        return Coverage(
            "llm_not_scheduled",
            "all_llm_calls_skipped",
            "present",
            tuple(evidence + ["skip_reason"]),
        )
    if not llm_rounds and refinements and skip_reasons == {"no_interpolants"}:
        return Coverage("no_spurious_ce", "no_spurious_interpolants", "present", tuple(evidence + ["skip_reason"]))
    return Coverage("complete", "task_summary_present", "present", tuple(evidence + ["summary"]))


def task_meta(
    task: str,
    task_dir: Path,
    analysis_logs: dict[str, dict],
    stock_logs: dict[str, dict],
    coverage: Coverage,
) -> dict:
    summary = load_json(task_dir / "task_summary.json")
    refinements, refinements_state = load_jsonl_state(task_dir / "refinements.jsonl")
    llm_rounds, llm_state = load_jsonl_state(task_dir / "llm_rounds.jsonl")
    if summary is not None:
        known_zero = coverage.status in {"no_spurious_ce", "llm_not_scheduled"}
        meta = {
            "task": task,
            "verdict": summary.get("verdict", "UNKNOWN"),
            "wall_s": summary.get("wall_s"),
            "refinements_cpa": summary.get("refinements"),
            "spurious_refinements": (
                len(refinements)
                if refinements_state is None
                else 0
                if known_zero
                else None
            ),
            "llm_rounds": summary.get("llm_rounds"),
            "llm_api_calls": summary.get("llm_api_calls"),
            "vguide_outcome": summary.get("vguide_outcome", ""),
            "incomplete": False,
            "stock_verdict": stock_logs.get(task, {}).get("verdict", ""),
        }
    else:
        fb = analysis_logs.get(task, {})
        meta = {
            "task": task,
            "verdict": fb.get("verdict", "UNKNOWN"),
            "wall_s": fb.get("wall_s"),
            "refinements_cpa": fb.get("refinements"),
            "spurious_refinements": len(refinements) if refinements_state is None else None,
            "llm_rounds": len({r.get("llm_round_index") for r in llm_rounds}) if llm_state is None else None,
            "llm_api_calls": len(llm_rounds) if llm_state is None else None,
            "vguide_outcome": "",
            "incomplete": True,
            "stock_verdict": stock_logs.get(task, {}).get("verdict", ""),
        }
    meta.update(coverage.fields())
    return meta


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

    refinements, refinements_state = load_jsonl_state(task_dir / "refinements.jsonl")
    llm_rounds, llm_state = load_jsonl_state(task_dir / "llm_rounds.jsonl")
    if refinements_state == "malformed":
        report.fail(task, "V2", "refinements.jsonl is malformed")
    if llm_state == "malformed":
        report.fail(task, "V2", "llm_rounds.jsonl is malformed")
    spurious_count = len(refinements)
    raw_ref_count = summary.get("refinements") if summary else spurious_count
    ref_count = raw_ref_count if isinstance(raw_ref_count, int) else None
    if summary and ref_count is None:
        report.fail(task, "V2", "task_summary refinements is not an integer")

    if ref_count == 0:
        if refinements:
            report.fail(task, "V3", f"expected 0 refinements.jsonl lines, got {spurious_count}")
    elif ref_count is not None and spurious_count not in (ref_count, ref_count - 1):
        report.warn(
            task,
            "V3",
            f"spurious lines {spurious_count} vs cpa refs {ref_count} (expected equal or cpa-1)",
        )

    if summary and "precision_final" not in summary:
        report.fail(task, "V8", "task_summary missing precision_final")

    log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path and log_path.is_file() else ""
    raw_llm_api_calls = summary.get("llm_api_calls") if summary else len(llm_rounds)
    llm_api_calls = raw_llm_api_calls if isinstance(raw_llm_api_calls, (int, float)) else None
    if summary and raw_llm_api_calls is not None and llm_api_calls is None:
        report.fail(task, "V2", "task_summary llm_api_calls is not numeric")

    if RE_LLM_ROUND.search(log_text):
        if llm_api_calls is not None and llm_api_calls <= 0 and llm_rounds:
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
    for task in sorted(present - set(tasks)):
        report.fail(task, "V1", "unexpected task directory (not in manifest)")

    for task in tasks:
        log_path = logs_dir / f"{task}.log" if logs_dir else None
        coverage = classify_coverage(
            dump_dir / "tasks" / task,
            log_path.read_text(encoding="utf-8", errors="replace") if log_path and log_path.is_file() else "",
        )
        if coverage.status == "dump_incomplete":
            report.fail(task, "V1", f"{coverage.reason} (coverage={coverage.status})")
        validate_task(task, dump_dir, log_path, dump_prompts, report)

    return report


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def sum_known(rows: list[dict], key: str) -> int | str:
    values = [v for r in rows if (v := as_int(r.get(key))) is not None]
    return sum(values) if values else ""


def median_known(rows: list[dict], key: str) -> int | str:
    values = sorted(v for r in rows if (v := as_int(r.get(key))) is not None)
    return values[len(values) // 2] if values else ""


def as_int(value: object) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value)
    return None


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

    coverage_by_task = {
        task: classify_coverage(
            tasks_root / task,
            (
                (logs_dir / f"{task}.log").read_text(encoding="utf-8", errors="replace")
                if logs_dir and (logs_dir / f"{task}.log").is_file()
                else ""
            ),
        )
        for task in tasks
    }
    meta_by_task = {
        task: task_meta(task, tasks_root / task, analysis_csv, stock_csv, coverage_by_task[task])
        for task in tasks
    }

    # --- context_budget.csv ---
    budget_rows: list[dict] = []
    for task in tasks:
        for row in load_jsonl_state(tasks_root / task / "llm_rounds.jsonl")[0]:
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
                    "prompt_profile": row.get("prompt_profile", ""),
                    "dual_prompt_mode": row.get("dual_prompt_mode", ""),
                    "prompt_tokens": usage.get("prompt_tokens", ""),
                    "completion_tokens": usage.get("completion_tokens", ""),
                    "total_tokens": usage.get("total_tokens", ""),
                    "prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens", ""),
                    "prompt_cache_miss_tokens": usage.get("prompt_cache_miss_tokens", ""),
                    "reasoning_tokens": details_c.get("reasoning_tokens", ""),
                    "latency_ms": row.get("latency_ms", ""),
                    "prompt_chars": row.get("prompt_chars", ""),
                    "chars_source": comps.get("source", ""),
                    "chars_contract": comps.get("contract", ""),
                    "chars_ce_summary": comps.get("ce_summary", comps.get("trace", "")),
                    "chars_rules": comps.get("rules", ""),
                    "chars_loop_heads": comps.get("loop_heads", ""),
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
            "prompt_profile",
            "dual_prompt_mode",
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
            "chars_ce_summary",
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
        meta = meta_by_task[task]
        llm_rounds_path = tasks_root / task / "llm_rounds.jsonl"
        known_zero = meta["coverage_status"] in {"no_spurious_ce", "llm_not_scheduled"}
        budget_task_rows.append(
            {
                **meta,
                "api_calls": (
                    0
                    if known_zero
                    else len(rows)
                    if llm_rounds_path.is_file() and meta["coverage_reason"] != "malformed_jsonl"
                    else ""
                ),
                "prompt_tokens_sum": 0 if known_zero else sum_known(rows, "prompt_tokens"),
                "completion_tokens_sum": 0 if known_zero else sum_known(rows, "completion_tokens"),
                "total_tokens_sum": 0 if known_zero else sum_known(rows, "total_tokens"),
                "latency_ms_sum": 0 if known_zero else sum_known(rows, "latency_ms"),
                "prompt_tokens_median": 0 if known_zero else median_known(rows, "prompt_tokens"),
            }
        )
    write_csv(
        out_dir / "context_budget_per_task.csv",
        [
            "task",
            "coverage_status",
            "coverage_reason",
            "dump_status",
            "coverage_evidence",
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
        meta = meta_by_task[task]
        precision_final = (load_json(task_dir / "task_summary.json") or {}).get(
            "precision_final", {}
        )
        solved = (
            meta["coverage_status"] in {"complete", "no_spurious_ce", "llm_not_scheduled"}
            and meta["verdict"] in ("TRUE", "FALSE")
        )
        had_llm = False

        for ref in load_jsonl_state(task_dir / "refinements.jsonl")[0]:
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
                        "coverage_status": meta["coverage_status"],
                        "coverage_reason": meta["coverage_reason"],
                        "verdict": meta["verdict"],
                        "stock_verdict": meta["stock_verdict"],
                        "refinement_index": ref.get("refinement_index"),
                        "predicate_id": vp.get("predicate_id"),
                        "source_profile": vp.get("source_profile", ""),
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
            "coverage_status",
            "coverage_reason",
            "verdict",
            "stock_verdict",
            "refinement_index",
            "predicate_id",
            "source_profile",
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
        meta = meta_by_task[task]
        oc = overlap_task.get(task, Counter())
        total_p = sum(oc.values())
        metrics_known = meta["coverage_status"] in {
            "complete",
            "no_spurious_ce",
            "llm_not_scheduled",
        }
        overlap_summary_rows.append(
            {
                "task": task,
                "coverage_status": meta["coverage_status"],
                "coverage_reason": meta["coverage_reason"],
                "verdict": meta["verdict"],
                "stock_verdict": meta["stock_verdict"],
                "llm_predicates": total_p if metrics_known else "",
                "redundant": oc.get("Redundant", 0) if metrics_known else "",
                "novel": oc.get("Novel", 0) if metrics_known else "",
                "orthogonal": oc.get("Orthogonal", 0) if metrics_known else "",
                "vacuous": oc.get("Vacuous", 0) if metrics_known else "",
                "pct_novel": round(100.0 * oc.get("Novel", 0) / total_p, 1) if total_p else (0 if metrics_known else ""),
            }
        )
    write_csv(
        out_dir / "overlap_summary.csv",
        [
            "task",
            "coverage_status",
            "coverage_reason",
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
    prompt_tokens = [t for r in budget_rows if (t := as_int(r["prompt_tokens"])) and t > 0]
    pt_sorted = sorted(prompt_tokens)
    verdict_counts = Counter(m["verdict"] for m in budget_task_rows)
    coverage_counts = Counter(m["coverage_status"] for m in budget_task_rows)
    stock_rescued = sum(
        1
        for m in budget_task_rows
        if m["coverage_status"] == "complete"
        and m["stock_verdict"] == "UNKNOWN"
        and m["verdict"] in ("TRUE", "FALSE")
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
        f"- Coverage: {dict(coverage_counts)}",
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
