#!/usr/bin/env python3
"""Unit tests for B5 predicate validator."""

import json
import sys
from pathlib import Path

# Add parent to path to import the validator module
sys.path.insert(0, str(Path(__file__).parent))
from b5_validate_candidates import (
    validate_predicate,
    validate_candidates,
    REJECT_INTERNAL_SYMBOL,
    REJECT_DEF_TERM,
    REJECT_SSA_NAME,
    REJECT_UNSUPPORTED_ARRAY,
    REJECT_UNSUPPORTED_BV_SHIFT,
    REJECT_UNSUPPORTED_OPERATOR,
)

PASS = 0
FAIL = 0


def check(name, is_valid, reason, predicate, expected_valid=None, expected_reason=None):
    global PASS, FAIL
    ok = True
    status = "   OK" if is_valid else "REJECT"
    report = f"{status:>6}  {name}: {predicate[:60]}"

    if expected_valid is not None and is_valid != expected_valid:
        ok = False
        report += f"  [expected valid={expected_valid}]"
    if expected_reason is not None and reason != expected_reason:
        ok = False
        report += f"  [expected reason={expected_reason}, got {reason}]"

    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(report)


# --- Accepted predicates ---
ACCEPTED = [
    "(= sn (bvmul i (_ bv2 32)))",
    "(= (bvurem x (_ bv2 32)) (bvurem y (_ bv2 32)))",
    "(bvsle i (_ bv8 32))",
    "(bvsge i (_ bv0 32))",
    "(= (bvadd y (_ bv1 32)) (_ bv1024 32))",
    "(= (bvsub (_ bv1024 32) y) (_ bv1 32))",
    "(bvsgt y (_ bv0 32))",
    "(= x (_ bv0 32))",
    "(bvslt n (_ bv10 32))",
    "(= (mod x 2) 0)",
    "(>= i 0)",
    "(= s (* i 255))",
]

print("=== Accepted (should all be valid) ===")
for p in ACCEPTED:
    is_valid, reason, explanation = validate_predicate(p)
    check(p, is_valid, reason, p, expected_valid=True, expected_reason=None)

# --- Rejected predicates ---
REJECTED = [
    ("(= |main::sn@2| (bvmul |main::i@1| (_ bv2 32)))", REJECT_INTERNAL_SYMBOL, "SSA pipe name"),
    ("(= .def_43 (_ bv0 32))", REJECT_DEF_TERM, ".def_ term"),
    ("(= (select a i) x)", REJECT_UNSUPPORTED_ARRAY, "select"),
    ("(= (bvshl x (_ bv1 32)) y)", REJECT_UNSUPPORTED_BV_SHIFT, "bvshl"),
    ("(= (store a i 5) a)", REJECT_UNSUPPORTED_ARRAY, "store"),
    ("(= (bvlshr x (_ bv1 32)) y)", REJECT_UNSUPPORTED_BV_SHIFT, "bvlshr"),
]

print()
print("=== Rejected (should all be invalid) ===")
for p, expected_code, _desc in REJECTED:
    is_valid, reason, explanation = validate_predicate(p)
    check(p, is_valid, reason, p, expected_valid=False, expected_reason=expected_code)

# --- Validate candidates dict ---
print()
print("=== Candidates dict validation ===")

candidates = {
    "N23": [
        "(= sn (bvmul i (_ bv2 32)))",
        "(= |main::sn@2| (bvmul |main::i@1| (_ bv2 32)))",
    ],
    "N19": [
        "(= (bvurem x 2) (bvurem y 2))",
        "(= (select a i) x)",
        "(= .def_43 (_ bv0 32))",
    ]
}
valid, rejected, report = validate_candidates(candidates)
print(f"  total: {report['total_input_predicates']}, valid: {report['valid_predicates']}, rejected: {report['rejected_predicates']}")

assert report['total_input_predicates'] == 5, f"Expected 5, got {report['total_input_predicates']}"
assert report['valid_predicates'] == 2, f"Expected 2, got {report['valid_predicates']}"
assert report['rejected_predicates'] == 3, f"Expected 3, got {report['rejected_predicates']}"
assert len(valid['N23']) == 1, f"Expected 1 valid for N23, got {len(valid.get('N23', []))}"
assert len(valid['N19']) == 1, f"Expected 1 valid for N19, got {len(valid.get('N19', []))}"
print("  Assertions passed")

# --- Summary ---
print()
print(f"{'='*40}")
print(f"PASS: {PASS}, FAIL: {FAIL}")
if FAIL > 0:
    print("SOME TESTS FAILED")
    sys.exit(1)
else:
    print("ALL TESTS PASSED")
