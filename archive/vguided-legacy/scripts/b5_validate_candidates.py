#!/usr/bin/env python3
"""B5 repair predicate validator — enforce output contract.

Usage as script:
  python3 b5_validate_candidates.py <repair_candidates.json> [--output-dir <dir>]

Usage as module:
  from b5_validate_candidates import validate_candidates, validate_predicate
"""

import json
import re
import sys
from pathlib import Path

# Reason codes
REJECT_INTERNAL_SYMBOL = "REJECT_INTERNAL_SYMBOL"
REJECT_DEF_TERM = "REJECT_DEF_TERM"
REJECT_SSA_NAME = "REJECT_SSA_NAME"
REJECT_UNSUPPORTED_ARRAY = "REJECT_UNSUPPORTED_ARRAY"
REJECT_UNSUPPORTED_BV_SHIFT = "REJECT_UNSUPPORTED_BV_SHIFT"
REJECT_UNSUPPORTED_OPERATOR = "REJECT_UNSUPPORTED_OPERATOR"

# Forbidden internal symbols
FORBIDDEN_PATTERNS = [
    (r'\|[a-z_]\w+::', REJECT_INTERNAL_SYMBOL, "contains internal SSA-encoded variable (|main::...)"),
    (r'\.def_\d+', REJECT_DEF_TERM, "contains internal solver term (.def_*)"),
]

# Forbidden operations (not in parser)
FORBIDDEN_OPS = [
    (r'\bselect\b', REJECT_UNSUPPORTED_ARRAY, "unsupported array select"),
    (r'\bstore\b', REJECT_UNSUPPORTED_ARRAY, "unsupported array store"),
    (r'\bbvshl\b', REJECT_UNSUPPORTED_BV_SHIFT, "unsupported bitvector shift (bvshl)"),
    (r'\bbvlshr\b', REJECT_UNSUPPORTED_BV_SHIFT, "unsupported bitvector logical shift (bvlshr)"),
    (r'\bbvashr\b', REJECT_UNSUPPORTED_BV_SHIFT, "unsupported bitvector arithmetic shift (bvashr)"),
]

# SSA name detection: variable name with @digit suffix not inside |...|
SSA_NAME_PATTERN = re.compile(r'(?<!\|)\b(\w+@\d+)\b')

# Allowed BV operators (also aliased in parser)
ALLOWED_OPS = {
    '=', '+', '-', '*', 'mod',
    'bvadd', 'bvmul', 'bvsub', 'bvurem', 'bvneg',
    '<', '>', '<=', '>=',
    'bvslt', 'bvsgt', 'bvsle', 'bvsge',
    'and', 'or', 'not',
    '_',  # (_ bvN 32) constants
}


def validate_predicate(predicate_text):
    """Validate a single predicate. Returns (is_valid, reason_code, explanation)."""
    stripped = predicate_text.strip()
    if not stripped:
        return False, REJECT_UNSUPPORTED_OPERATOR, "empty predicate"

    # Check forbidden patterns
    for pattern, code, explanation in FORBIDDEN_PATTERNS:
        if re.search(pattern, stripped):
            return False, code, explanation

    # Check SSA names (bare @ suffix outside pipes)
    ssa_match = SSA_NAME_PATTERN.search(stripped)
    if ssa_match:
        return False, REJECT_SSA_NAME, f"contains SSA-encoded name: {ssa_match.group(1)}"

    # Check forbidden operations
    for pattern, code, explanation in FORBIDDEN_OPS:
        if re.search(pattern, stripped):
            return False, code, explanation

    return True, None, None


def extract_operators(predicate_text):
    """Extract top-level S-expression operators for unsupported-op check."""
    ops = set()
    # Match (op at start of any S-expression
    for m in re.finditer(r'\(\s*(\w+)', predicate_text):
        ops.add(m.group(1))
    return ops


def validate_candidates(candidates_json):
    """Validate a candidates dict {location: [pred1, pred2, ...]}.

    Returns:
        (valid_candidates, rejected_list, validation_report)
    """
    if not isinstance(candidates_json, dict):
        return {}, [{"predicate": str(candidates_json),
                     "reason": REJECT_UNSUPPORTED_OPERATOR,
                     "explanation": "input is not a valid candidates dict"}], {"error": "not a dict"}

    valid = {}
    rejected = []

    for location, predicates in candidates_json.items():
        for pred in predicates:
            is_ok, code, explanation = validate_predicate(pred)
            if is_ok:
                valid.setdefault(location, []).append(pred)
            else:
                rejected.append({
                    "location": location,
                    "predicate": pred,
                    "reason": code,
                    "explanation": explanation
                })

    # Additional: check for unsupported operators in "valid" predicates
    # (operators not in the parser alias list)
    valid_filtered = {}
    for location, predicates in list(valid.items()):
        for pred in predicates:
            ops = extract_operators(pred)
            unsupported = ops - ALLOWED_OPS
            if unsupported:
                rejected.append({
                    "location": location,
                    "predicate": pred,
                    "reason": REJECT_UNSUPPORTED_OPERATOR,
                    "explanation": f"unsupported operators: {', '.join(sorted(unsupported))}"
                })
            else:
                valid_filtered.setdefault(location, []).append(pred)
    valid = valid_filtered

    total_preds = sum(len(v) for v in candidates_json.values())
    valid_count = sum(len(v) for v in valid.values())
    rejected_count = len(rejected)

    report = {
        "total_input_predicates": total_preds,
        "valid_predicates": valid_count,
        "rejected_predicates": rejected_count,
        "valid_locations": len(valid),
        "rejected_details": rejected
    }

    return valid, rejected, report


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 b5_validate_candidates.py <repair_candidates.json> [--output-dir <dir>]")
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = None
    if len(sys.argv) > 3 and sys.argv[2] == "--output-dir":
        output_dir = sys.argv[3]

    with open(input_file) as f:
        candidates = json.load(f)

    valid, rejected, report = validate_candidates(candidates)

    print(f"Total input predicates: {report['total_input_predicates']}")
    print(f"Valid predicates: {report['valid_predicates']}")
    print(f"Rejected predicates: {report['rejected_predicates']}")
    print()

    if rejected:
        print("=== Rejected ===")
        for r in rejected:
            print(f"  [{r['reason']}] {r.get('location', '?')}: {r['predicate'][:100]}")
            print(f"    {r['explanation']}")
        print()

    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "repair_candidates_validated.json").write_text(json.dumps(valid, indent=2))
        (out / "rejected_candidates.json").write_text(json.dumps(rejected, indent=2))
        print(f"Validated candidates → {out / 'repair_candidates_validated.json'}")
        print(f"Rejected candidates → {out / 'rejected_candidates.json'}")
    else:
        print("=== Validated Candidates ===")
        print(json.dumps(valid, indent=2))


if __name__ == "__main__":
    main()
