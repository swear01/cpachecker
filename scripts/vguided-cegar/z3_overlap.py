"""Z3 entailment checks for VGuide overlap / PCS (see OVERLAP_AND_PCS.md)."""

from __future__ import annotations

import re

try:
    from z3 import Solver, unsat
except ImportError:
    Solver = None  # type: ignore
    unsat = None  # type: ignore


def balanced_exprs(s: str, opener: str = "(declare-fun") -> list[str]:
    out: list[str] = []
    i = 0
    while True:
        j = s.find(opener, i)
        if j < 0:
            break
        depth = 0
        for k in range(j, len(s)):
            if s[k] == "(":
                depth += 1
            elif s[k] == ")":
                depth -= 1
                if depth == 0:
                    out.append(s[j : k + 1])
                    i = k + 1
                    break
        else:
            break
    return out


def assert_exprs(s: str) -> list[str]:
    return balanced_exprs(s, "(assert")


def assert_body(assert_expr: str) -> str:
    return assert_expr[len("(assert ") : -1]


def declare_names(smt: str) -> set[str]:
    names: set[str] = set()
    for d in balanced_exprs(smt):
        m = re.match(r"\(declare-fun (\S+)", d)
        if m:
            names.add(m.group(1))
    return names


def same_symbol_namespace(antecedent_parts: list[str], consequent_smt: str) -> bool:
    """True when consequent symbols use the same SSA names as antecedent (no |x| vs |x@2| mix)."""
    q_names = declare_names(consequent_smt)
    if not q_names:
        return False
    ant_names: set[str] = set()
    for part in antecedent_parts:
        ant_names |= declare_names(part)
    return q_names <= ant_names


def entails(antecedent_parts: list[str], consequent_smt: str, timeout_ms: int) -> str:
    """Check ⊨: UNSAT(⋀antecedent ∧ ¬consequent). Returns yes|no|unknown|skip."""
    if Solver is None:
        return "skip"
    ant_bodies: list[str] = []
    all_decls: list[str] = []
    for part in antecedent_parts:
        if not part or not part.strip():
            continue
        all_decls.extend(balanced_exprs(part))
        for a in assert_exprs(part):
            ant_bodies.append(assert_body(a))
    c_asserts = assert_exprs(consequent_smt)
    if not ant_bodies or not c_asserts:
        return "skip"
    c_body = assert_body(c_asserts[0])
    all_decls.extend(balanced_exprs(consequent_smt))
    decls_u = list(dict.fromkeys(all_decls))
    ant_body = ant_bodies[0] if len(ant_bodies) == 1 else "(and " + " ".join(ant_bodies) + ")"
    script = (
        "(set-logic QF_AUFBV)\n"
        + "\n".join(decls_u)
        + f"\n(assert {ant_body})\n(assert (not {c_body}))\n"
    )
    s = Solver()
    s.set("timeout", timeout_ms)
    try:
        s.from_string(script)
        r = s.check()
        if r == unsat:
            return "yes"
        if str(r) == "sat":
            return "no"
        return "unknown"
    except Exception:
        return "unknown"


def z3_float(result: str) -> float:
    return 1.0 if result == "yes" else 0.0 if result == "no" else 0.5 if result == "unknown" else 0.0


def classify_overlap_z3(r_i: float, r_p: float, r_t: float) -> str:
    """Redundant if q entailed by I, P, or block (max component ≥ 0.9)."""
    mx = max(r_i, r_p, r_t)
    if mx >= 0.9:
        return "Redundant"
    if mx <= 0.1:
        return "Novel"
    return "Orthogonal"


def compute_overlap_z3(
    q_smt: str,
    loop_head: str,
    interpolants: list[dict],
    precision_before: dict,
    block_smt: str,
    timeout_ms: int = 8000,
) -> tuple[str, float, float, float, float, dict]:
    """
    Returns (overlap_class, r_i, r_t, r_p, n, status_dict).
    R_T = block ⊨ q (trace/block redundancy), NOT trace necessity.
    R_P skipped when precision uses a different SSA namespace than q.
    """
    i_smt = None
    for itp in interpolants:
        if itp.get("node") == loop_head:
            i_smt = itp.get("smt", "")
            break
    if not i_smt and interpolants:
        i_smt = interpolants[0].get("smt", "")

    r_i_s = entails([i_smt], q_smt, timeout_ms) if i_smt else "skip"
    r_i = z3_float(r_i_s)

    prec = precision_before.get(loop_head, [])
    prec_list = prec if isinstance(prec, list) else []
    if prec_list and same_symbol_namespace(prec_list, q_smt):
        r_p_s = entails(prec_list, q_smt, timeout_ms)
    else:
        r_p_s = "skip"
    r_p = z3_float(r_p_s) if r_p_s != "skip" else 0.0

    r_t_s = entails([block_smt], q_smt, timeout_ms) if block_smt else "skip"
    r_t = z3_float(r_t_s) if r_t_s != "skip" else 0.0

    n = 1.0 - max(r_i, r_p)
    overlap = classify_overlap_z3(r_i, r_p, r_t)
    status = {"R_I": r_i_s, "R_P": r_p_s, "R_T": r_t_s}
    return overlap, r_i, r_t, r_p, n, status
