#!/usr/bin/env python3
"""Render and run the VGuide-NLA oracle-capacity k-induction smoke.

The catalog stores integer-theory polynomial candidates. CPAchecker converts them to the
program's bit-vector types with its existing INT2BV precision converter, imports them through
``bmc.kinduction.predicatePrecisionFile``, and proves or rejects them with the stock BMC and
k-induction implementation.
"""
from __future__ import annotations

import argparse
import csv
import dataclasses
import hashlib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable, Sequence

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CATALOG = (
    REPO / "docs/vguided-cegar/evaluation/nla_oracle_smoke_candidates.json"
)
DEFAULT_BENCHMARK_ROOT = Path.home() / "sv-benchmarks/c"
DEFAULT_OUTPUT = REPO / "output/vguide/experiments/nla_oracle_capacity"
K_INDUCTION_CONFIG = REPO / "config/components/kInduction/kInduction.properties"
KI_PDR_CONFIG = REPO / "config/components/kInduction/kInduction-kipdrInvariants.properties"
KI_PDR_LATE_CONFIG = (
    REPO / "config/components/kInduction/kInduction-kipdr-lateInvariants.properties"
)
PDR_CONFIG = REPO / "config/unmaintained/components/kInduction/pdr.properties"
REACHABILITY_SPEC = REPO / "config/specification/sv-comp-reachability.spc"
CONSUMER_CONFIGS = {
    "kinduction": K_INDUCTION_CONFIG,
    "kipdr": KI_PDR_CONFIG,
    "kipdr-late": KI_PDR_LATE_CONFIG,
    "pdr": PDR_CONFIG,
    "pdr-abstraction": PDR_CONFIG,
}

SYMBOL = re.compile(r"\|[^|]+\|")
SEXPR_TOKEN = re.compile(r"\(|\)|\|[^|]+\||[^\s()]+")
VERIFICATION_RESULT = re.compile(r"Verification result:\s*(TRUE|FALSE|UNKNOWN)", re.I)
WALL_TIME = re.compile(r"Total time for CPAchecker:\s*([0-9.]+)s", re.I)
INVARIANTS_PROPOSED = re.compile(r"Number of invariants proposed:\s*(\d+)", re.I)
ORACLE_PREDICATES_SEEDED = re.compile(r"PDR oracle predicates seeded:\s*(\d+)", re.I)
ORACLE_ROOTS_CONFIRMED = re.compile(r"PDR oracle roots confirmed:\s*(\d+)", re.I)
TARGET_AFTER_ORACLE_ROOT = re.compile(
    r"Target confirmed after oracle root:\s*(true|false)", re.I
)


class CatalogError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class TaskSpec:
    task: str
    source: Path
    yml: Path
    expected: str
    source_sha256: str
    yml_sha256: str
    predicates: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class Catalog:
    version: int
    tasks: tuple[TaskSpec, ...]


@dataclasses.dataclass(frozen=True)
class LogResult:
    result: str
    wall_s: float
    invariants_proposed: int
    oracle_predicates_seeded: int
    oracle_roots_confirmed: int
    target_after_oracle_root: bool
    note: str


@dataclasses.dataclass(frozen=True)
class Comparison:
    tasks: int
    stock_solved: int
    oracle_solved: int
    new: int
    lost: int
    wrong: int


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _required_string(raw: dict[str, object], key: str, task: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise CatalogError(f"task {task!r}: {key} must be a non-empty string")
    return value


def load_catalog(
    path: Path,
    benchmark_root: Path,
    *,
    expected_count: int | None = 12,
    verify_hashes: bool = True,
) -> Catalog:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict) or raw.get("version") != 1:
        raise CatalogError("catalog version must be 1")
    raw_tasks = raw.get("tasks")
    if not isinstance(raw_tasks, list):
        raise CatalogError("catalog tasks must be a list")
    if expected_count is not None and len(raw_tasks) != expected_count:
        raise CatalogError(f"catalog must contain {expected_count} tasks, got {len(raw_tasks)}")

    seen: set[str] = set()
    tasks: list[TaskSpec] = []
    for raw_task in raw_tasks:
        if not isinstance(raw_task, dict):
            raise CatalogError("each task must be an object")
        task = _required_string(raw_task, "task", "<unknown>")
        if task in seen:
            raise CatalogError(f"duplicate task {task!r}")
        seen.add(task)
        source_rel = Path(_required_string(raw_task, "source", task))
        yml_rel = Path(_required_string(raw_task, "yml", task))
        if source_rel.is_absolute() or yml_rel.is_absolute():
            raise CatalogError(f"task {task!r}: source and yml paths must be relative")
        source = benchmark_root / source_rel
        yml = benchmark_root / yml_rel
        if not source.is_file():
            raise CatalogError(f"task {task!r}: missing source {source}")
        if not yml.is_file():
            raise CatalogError(f"task {task!r}: missing YAML {yml}")
        expected = _required_string(raw_task, "expected", task).upper()
        if expected not in {"TRUE", "FALSE"}:
            raise CatalogError(f"task {task!r}: expected must be TRUE or FALSE")
        source_hash = _required_string(raw_task, "source_sha256", task)
        yml_hash = _required_string(raw_task, "yml_sha256", task)
        if verify_hashes:
            actual = sha256(source)
            if actual != source_hash:
                raise CatalogError(
                    f"task {task!r}: source SHA-256 mismatch: {actual} != {source_hash}"
                )
            actual = sha256(yml)
            if actual != yml_hash:
                raise CatalogError(
                    f"task {task!r}: YAML SHA-256 mismatch: {actual} != {yml_hash}"
                )
        raw_predicates = raw_task.get("predicates")
        if not isinstance(raw_predicates, list) or not raw_predicates:
            raise CatalogError(f"task {task!r}: predicates must be a non-empty list")
        predicates: list[str] = []
        for predicate in raw_predicates:
            if not isinstance(predicate, str) or not predicate.startswith("("):
                raise CatalogError(f"task {task!r}: invalid predicate {predicate!r}")
            if not SYMBOL.search(predicate):
                raise CatalogError(
                    f"task {task!r}: predicate must use quoted CPAchecker symbols: {predicate}"
                )
            validate_converter_compatible(predicate, task)
            predicates.append(predicate)
        tasks.append(
            TaskSpec(
                task=task,
                source=source_rel,
                yml=yml_rel,
                expected=expected,
                source_sha256=source_hash,
                yml_sha256=yml_hash,
                predicates=tuple(predicates),
            )
        )
    return Catalog(version=1, tasks=tuple(tasks))


def _parse_sexpr(text: str) -> object:
    tokens = SEXPR_TOKEN.findall(text)
    position = 0

    def parse_one() -> object:
        nonlocal position
        if position >= len(tokens):
            raise CatalogError("unexpected end of SMT-LIB expression")
        token = tokens[position]
        position += 1
        if token != "(":
            if token == ")":
                raise CatalogError("unexpected ')' in SMT-LIB expression")
            return token
        result: list[object] = []
        while position < len(tokens) and tokens[position] != ")":
            result.append(parse_one())
        if position >= len(tokens):
            raise CatalogError("missing ')' in SMT-LIB expression")
        position += 1
        return result

    parsed = parse_one()
    if position != len(tokens):
        raise CatalogError("trailing tokens in SMT-LIB expression")
    return parsed


def validate_converter_compatible(predicate: str, task: str) -> None:
    """Reject shapes unsupported by CPAchecker's INT2BV precision converter."""

    parsed = _parse_sexpr(predicate)

    def visit(node: object) -> None:
        if not isinstance(node, list):
            return
        if not node or not isinstance(node[0], str):
            raise CatalogError(f"task {task!r}: invalid SMT-LIB application")
        operator = node[0]
        operands = node[1:]
        if operator in {"+", "-", "*", "=", "<", "<=", ">", ">="} and len(operands) != 2:
            raise CatalogError(
                f"task {task!r}: operator {operator} requires 2 operands for INT2BV conversion"
            )
        if operator == "not" and len(operands) != 1:
            raise CatalogError(f"task {task!r}: operator not requires 1 operand")
        for operand in operands:
            visit(operand)

    visit(parsed)


def _conjunction(predicates: Sequence[str]) -> str:
    result = predicates[-1]
    for predicate in reversed(predicates[:-1]):
        result = f"(and {predicate} {result})"
    return result


def render_predicate_map(task: TaskSpec, *, shape: str = "atomic") -> str:
    symbols = sorted({symbol for pred in task.predicates for symbol in SYMBOL.findall(pred)})
    declarations = [f"(declare-fun {symbol} () Int)" for symbol in symbols]
    if shape == "atomic":
        assertions = [f"(assert {predicate})" for predicate in task.predicates]
    elif shape == "supporting-first":
        # StaticCandidateProvider iterates candidates in reverse insertion order.
        assertions = [f"(assert {predicate})" for predicate in reversed(task.predicates)]
    elif shape == "conjunction":
        assertions = [f"(assert {_conjunction(task.predicates)})"]
    else:
        raise ValueError(f"unsupported candidate shape {shape!r}")
    return "\n".join([*declarations, "", "*:", *assertions, ""])


def select_tasks(catalog: Catalog, names: Sequence[str]) -> Catalog:
    if not names:
        return catalog
    requested = set(names)
    known = {task.task for task in catalog.tasks}
    unknown = sorted(requested - known)
    if unknown:
        raise CatalogError(f"unknown requested tasks: {', '.join(unknown)}")
    return Catalog(
        version=catalog.version,
        tasks=tuple(task for task in catalog.tasks if task.task in requested),
    )


def build_command(
    *,
    repo: Path,
    task: TaskSpec,
    benchmark_root: Path,
    output_dir: Path,
    timelimit: int,
    heap: str,
    predicate_map: Path | None,
    encoding: str,
    consumer: str = "kinduction",
    oracle_mode: str = "separate",
) -> list[Path | str]:
    try:
        config = CONSUMER_CONFIGS[consumer]
    except KeyError as error:
        raise ValueError(f"unsupported consumer {consumer!r}") from error
    command: list[Path | str] = [
        repo / "scripts/cpa.sh",
        "--heap",
        heap,
        "--config",
        repo / config.relative_to(REPO),
        "--spec",
        repo / "config/specification/sv-comp-reachability.spc",
        "--timelimit",
        f"{timelimit}s",
        "--stats",
        "--no-output-files",
        "--output-path",
        output_dir,
    ]
    if encoding == "nia":
        command.extend(
            [
                "--option",
                "cpa.predicate.encodeBitvectorAs=INTEGER",
                "--option",
                "cpa.predicate.useNonlinearArithmeticForIntAsBv=true",
                "--option",
                "solver.nonLinearArithmetic=USE",
                "--option",
                "cpa.predicate.addRangeConstraintsForNondet=true",
                "--option",
                "cpa.predicate.handleFieldAccess=false",
                "--option",
                "solver.solver=Z3",
            ]
        )
    elif encoding != "bv":
        raise ValueError(f"unsupported encoding {encoding!r}")
    if consumer == "pdr-abstraction":
        command.extend(
            [
                "--option",
                "pdr.abstractionStrategy=ALLSAT_BASED_PREDICATE_ABSTRACTION",
                "--option",
                "pdr.liftingStrategy=ABSTRACTION_BASED_LIFTING",
            ]
        )
    if predicate_map is not None:
        if consumer.startswith("pdr"):
            if oracle_mode not in {"root", "conjunctive_root", "abstraction", "both"}:
                raise ValueError(
                    f"unsupported oracle mode {oracle_mode!r} for direct PDR"
                )
            command.extend(
                [
                    "--option",
                    f"pdr.oraclePredicatePrecisionFile={predicate_map}",
                    "--option",
                    f"pdr.oracleMode={oracle_mode.upper()}",
                    "--option",
                    "bmc.kinduction.reuse.pred.strategy=GLOBAL",
                ]
            )
        else:
            if oracle_mode not in {"separate", "conjunction"}:
                raise ValueError(
                    f"unsupported oracle mode {oracle_mode!r} for k-induction"
                )
            command.extend(
                [
                    "--option",
                    f"bmc.kinduction.predicatePrecisionFile={predicate_map}",
                    "--option",
                    "bmc.kinduction.reuse.pred.strategy=GLOBAL",
                ]
            )
            if oracle_mode == "conjunction":
                command.extend(
                    [
                        "--option",
                        "bmc.kinduction.reuse.pred.conjunction=true",
                    ]
                )
        if encoding == "bv":
            command.extend(
                [
                    "--option",
                    "cpa.predicate.abstraction.initialPredicates.encodePredicates=INT2BV",
                ]
            )
    command.append(benchmark_root / task.source)
    return command


def parse_log(text: str) -> LogResult:
    result_match = VERIFICATION_RESULT.search(text)
    result = result_match.group(1).upper() if result_match else "UNKNOWN"
    wall_match = WALL_TIME.search(text)
    wall_s = float(wall_match.group(1)) if wall_match else 0.0
    invariant_match = INVARIANTS_PROPOSED.search(text)
    invariants = int(invariant_match.group(1)) if invariant_match else 0
    seeded_match = ORACLE_PREDICATES_SEEDED.search(text)
    seeded = int(seeded_match.group(1)) if seeded_match else 0
    roots_match = ORACLE_ROOTS_CONFIRMED.search(text)
    roots = int(roots_match.group(1)) if roots_match else 0
    target_after_match = TARGET_AFTER_ORACLE_ROOT.search(text)
    target_after = bool(
        target_after_match and target_after_match.group(1).lower() == "true"
    )
    if "Invalid configuration" in text:
        note = "invalid_configuration"
    elif (
        "Could not read precision" in text
        or "Parsing failed in line" in text
        or "problem while parsing the formula" in text
    ):
        note = "candidate_parse"
    elif (
        "CPU-time limit" in text and "has elapsed" in text
    ) or "walltime limit" in text.lower() or "outer timeout expired" in text:
        note = "timeout"
    elif "SolverException" in text or "Solver Failure" in text:
        note = "solver_failure"
    elif "Exception in thread \"main\"" in text:
        note = "exception"
    elif result in {"TRUE", "FALSE"}:
        note = "solved"
    else:
        note = "unknown"
    return LogResult(result, wall_s, invariants, seeded, roots, target_after, note)


def compare_arms(rows: Iterable[tuple[str, str, str, str]]) -> Comparison:
    tasks = stock_solved = oracle_solved = new = lost = wrong = 0
    for _task, expected, stock, oracle in rows:
        tasks += 1
        stock_ok = stock in {"TRUE", "FALSE"}
        oracle_ok = oracle in {"TRUE", "FALSE"}
        stock_solved += int(stock_ok)
        oracle_solved += int(oracle_ok)
        new += int(not stock_ok and oracle == expected)
        lost += int(stock == expected and not oracle_ok)
        wrong += int(oracle_ok and oracle != expected)
    return Comparison(tasks, stock_solved, oracle_solved, new, lost, wrong)


def infrastructure_failures(
    arm_rows: dict[str, Sequence[dict[str, str]]],
) -> list[str]:
    failure_notes = {
        "candidate_parse",
        "exception",
        "invalid_configuration",
        "solver_failure",
    }
    return [
        f"{arm}/{row['task']}:{row['note']}"
        for arm, rows in arm_rows.items()
        for row in rows
        if row["note"] in failure_notes
    ]


def materialize_predicate_maps(
    catalog: Catalog, output_dir: Path, *, shape: str = "atomic"
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for task in catalog.tasks:
        path = output_dir / f"{task.task}.smt2"
        path.write_text(render_predicate_map(task, shape=shape))
        paths[task.task] = path.resolve()
    return paths


def _git_value(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def write_provenance(
    *,
    repo: Path,
    catalog_path: Path,
    benchmark_root: Path,
    output: Path,
    timelimit: int,
    heap: str,
    encoding: str,
    candidate_shape: str,
    consumer: str,
    oracle_mode: str,
    jobs: int,
) -> None:
    version_output = subprocess.check_output(
        [str(repo / "scripts/cpa.sh"), "--version"],
        cwd=repo,
        stderr=subprocess.STDOUT,
        text=True,
    )
    version = next(
        (line.strip() for line in version_output.splitlines() if line.startswith("CPAchecker ")),
        "unknown",
    )
    jar = repo / "cpachecker.jar"
    config = CONSUMER_CONFIGS[consumer]
    payload = {
        "commit": _git_value(repo, "rev-parse", "HEAD"),
        "dirty": bool(_git_value(repo, "status", "--short")),
        "catalog": str(catalog_path.resolve()),
        "catalog_sha256": sha256(catalog_path),
        "benchmark_root": str(benchmark_root.resolve()),
        "consumer": consumer,
        "oracle_mode": oracle_mode,
        "jobs": jobs,
        "config": str(config.relative_to(REPO)),
        "config_sha256": sha256(config),
        "spec": str(REACHABILITY_SPEC.relative_to(REPO)),
        "spec_sha256": sha256(REACHABILITY_SPEC),
        "timelimit_s": timelimit,
        "heap": heap,
        "encoding": encoding,
        "candidate_shape": candidate_shape,
        "cpachecker_version": version,
        "cpachecker_jar_sha256": sha256(jar),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def run_arm(
    *,
    arm: str,
    catalog: Catalog,
    benchmark_root: Path,
    output_root: Path,
    timelimit: int,
    heap: str,
    encoding: str,
    consumer: str,
    oracle_mode: str,
    jobs: int,
    predicate_maps: dict[str, Path],
    dry_run: bool,
) -> list[dict[str, str]]:
    arm_dir = output_root / arm
    logs_dir = arm_dir / "logs"
    cpa_output = arm_dir / "cpa-output"
    logs_dir.mkdir(parents=True, exist_ok=True)
    cpa_output.mkdir(parents=True, exist_ok=True)
    if jobs < 1:
        raise ValueError("jobs must be at least 1")

    def run_task(task: TaskSpec) -> dict[str, str]:
        predicate_map = predicate_maps[task.task] if arm == "oracle" else None
        command = build_command(
            repo=REPO,
            task=task,
            benchmark_root=benchmark_root,
            output_dir=cpa_output / task.task,
            timelimit=timelimit,
            heap=heap,
            predicate_map=predicate_map,
            encoding=encoding,
            consumer=consumer,
            oracle_mode=oracle_mode,
        )
        log_path = logs_dir / f"{task.task}.log"
        if dry_run:
            text = "DRY RUN: " + " ".join(str(part) for part in command) + "\n"
        else:
            try:
                completed = subprocess.run(
                    [str(part) for part in command],
                    cwd=REPO,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=timelimit + 30,
                    check=False,
                )
                text = completed.stdout
            except subprocess.TimeoutExpired as error:
                stdout = error.stdout or ""
                if isinstance(stdout, bytes):
                    stdout = stdout.decode(errors="replace")
                text = stdout + "\nHARNESS: outer timeout expired\n"
        log_path.write_text(text)
        parsed = parse_log(text)
        return {
            "task": task.task,
            "source": str(task.source),
            "expected": task.expected,
            "result": parsed.result,
            "wall_s": f"{parsed.wall_s:.3f}",
            "invariants_proposed": str(parsed.invariants_proposed),
            "oracle_predicates_seeded": str(parsed.oracle_predicates_seeded),
            "oracle_roots_confirmed": str(parsed.oracle_roots_confirmed),
            "target_after_oracle_root": str(parsed.target_after_oracle_root),
            "note": "dry_run" if dry_run else parsed.note,
            "log": str(log_path),
            "predicate_map": str(predicate_map or ""),
        }

    with ThreadPoolExecutor(max_workers=jobs) as executor:
        rows = list(executor.map(run_task, catalog.tasks))
    summary = arm_dir / "summary.csv"
    with summary.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def write_comparison(
    stock: Sequence[dict[str, str]], oracle: Sequence[dict[str, str]], output: Path
) -> Comparison:
    stock_by_task = {row["task"]: row for row in stock}
    oracle_by_task = {row["task"]: row for row in oracle}
    if stock_by_task.keys() != oracle_by_task.keys():
        raise ValueError("stock and oracle summaries contain different tasks")
    rows = []
    inputs = []
    for task in stock_by_task:
        s = stock_by_task[task]
        o = oracle_by_task[task]
        inputs.append((task, s["expected"], s["result"], o["result"]))
        rows.append(
            {
                "task": task,
                "expected": s["expected"],
                "stock": s["result"],
                "oracle": o["result"],
                "new": str(s["result"] not in {"TRUE", "FALSE"} and o["result"] == s["expected"]),
                "lost": str(s["result"] == s["expected"] and o["result"] not in {"TRUE", "FALSE"}),
                "wrong": str(o["result"] in {"TRUE", "FALSE"} and o["result"] != s["expected"]),
            }
        )
    comparison = compare_arms(inputs)
    output.mkdir(parents=True, exist_ok=True)
    with (output / "comparison.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output / "comparison.json").write_text(
        json.dumps(dataclasses.asdict(comparison), indent=2, sort_keys=True) + "\n"
    )
    return comparison


def _load_summary(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as file:
        return list(csv.DictReader(file))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--benchmark-root", type=Path, default=DEFAULT_BENCHMARK_ROOT)
    parser.add_argument("--expected-count", type=int, default=12)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("validate")
    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT / "predicate-maps")
    render_parser.add_argument(
        "--candidate-shape",
        choices=("atomic", "supporting-first", "conjunction"),
        default="atomic",
    )

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    run_parser.add_argument("--arm", choices=("stock", "oracle", "both"), default="both")
    run_parser.add_argument("--timelimit", type=int, default=60)
    run_parser.add_argument("--heap", default="4G")
    run_parser.add_argument("--jobs", type=int, default=1)
    run_parser.add_argument("--encoding", choices=("bv", "nia"), default="bv")
    run_parser.add_argument(
        "--consumer",
        choices=("kinduction", "kipdr", "kipdr-late", "pdr", "pdr-abstraction"),
        default="kinduction",
    )
    run_parser.add_argument(
        "--oracle-mode",
        choices=(
            "separate",
            "conjunction",
            "root",
            "conjunctive_root",
            "abstraction",
            "both",
        ),
        default="separate",
    )
    run_parser.add_argument(
        "--candidate-shape",
        choices=("atomic", "supporting-first", "conjunction"),
        default="atomic",
    )
    run_parser.add_argument("--task", action="append", default=[])
    run_parser.add_argument("--dry-run", action="store_true")

    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)

    args = parser.parse_args(argv)
    catalog = load_catalog(
        args.catalog,
        args.benchmark_root,
        expected_count=args.expected_count,
        verify_hashes=True,
    )
    if args.command == "validate":
        print(f"OK: catalog version={catalog.version} tasks={len(catalog.tasks)}")
        return 0
    if args.command == "render":
        paths = materialize_predicate_maps(
            catalog, args.output, shape=args.candidate_shape
        )
        print(f"rendered {len(paths)} predicate maps under {args.output}")
        return 0
    if args.command == "compare":
        comparison = write_comparison(
            _load_summary(args.output / "stock/summary.csv"),
            _load_summary(args.output / "oracle/summary.csv"),
            args.output,
        )
        print(json.dumps(dataclasses.asdict(comparison), sort_keys=True))
        return 0

    catalog = select_tasks(catalog, args.task)
    output = args.output.resolve()
    maps = materialize_predicate_maps(
        catalog, output / "predicate-maps", shape=args.candidate_shape
    )
    write_provenance(
        repo=REPO,
        catalog_path=args.catalog,
        benchmark_root=args.benchmark_root,
        output=output / "provenance.json",
        timelimit=args.timelimit,
        heap=args.heap,
        encoding=args.encoding,
        candidate_shape=args.candidate_shape,
        consumer=args.consumer,
        oracle_mode=args.oracle_mode,
        jobs=args.jobs,
    )
    arms = ("stock", "oracle") if args.arm == "both" else (args.arm,)
    arm_rows: dict[str, list[dict[str, str]]] = {}
    for arm in arms:
        arm_rows[arm] = run_arm(
            arm=arm,
            catalog=catalog,
            benchmark_root=args.benchmark_root,
            output_root=output,
            timelimit=args.timelimit,
            heap=args.heap,
            encoding=args.encoding,
            consumer=args.consumer,
            oracle_mode=args.oracle_mode,
            jobs=args.jobs,
            predicate_maps=maps,
            dry_run=args.dry_run,
        )
    if "stock" in arm_rows and "oracle" in arm_rows:
        comparison = write_comparison(arm_rows["stock"], arm_rows["oracle"], output)
        print(json.dumps(dataclasses.asdict(comparison), sort_keys=True))
    else:
        print(f"completed arm={arms[0]} tasks={len(catalog.tasks)}")
    failures = infrastructure_failures(arm_rows)
    if failures:
        print("infrastructure failures: " + ", ".join(failures))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
