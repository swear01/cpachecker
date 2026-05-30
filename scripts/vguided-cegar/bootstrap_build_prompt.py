#!/usr/bin/env python3
"""Bootstrap prompt builder — generate initial predicates for zero-context timeouts.

Usage: python3 bootstrap_build_prompt.py <benchmark.c|.i> [--output prompt.md]
"""

import os, re, sys
from pathlib import Path


def extract_assertion(source):
    for m in re.finditer(r'__VERIFIER_assert\s*\(', source):
        start = m.end()
        depth, i = 1, start
        while i < len(source) and depth > 0:
            if source[i] == '(': depth += 1
            elif source[i] == ')': depth -= 1
            i += 1
        if depth != 0: continue
        expr = source[start:i-1].strip()
        if re.match(r'^(int|unsigned|void|char|long|short|float|double|bool|_Bool)\s+\w+\s*$', expr):
            continue
        return expr
    return ""


def build_prompt(source, assertion):
    lines = []
    lines.append("# Initial Precision Bootstrap\n")
    lines.append("You are helping a CEGAR-based software verifier (CPAchecker) that is stuck on a loop benchmark.\n")
    lines.append("\n")
    lines.append("## The Problem\n")
    lines.append("CPAchecker's predicate abstraction cannot complete even one CEGAR refinement\n")
    lines.append("within the time budget (ZERO_CONTEXT_TIMEOUT). The initial abstraction is too weak\n")
    lines.append("to analyze any counterexample trace.\n")
    lines.append("\n")
    lines.append("## Source Code\n")
    lines.append("```c\n")
    lines.append(source.rstrip())
    lines.append("\n```\n")
    lines.append("\n")

    if assertion:
        lines.append("## Target Assertion\n")
        lines.append(f"```c\n__VERIFIER_assert({assertion});\n```\n")
        vars_ = list(set(re.findall(r'\b([a-zA-Z_]\w*)\b', assertion)))
        lines.append(f"Assertion variables: {', '.join(vars_)}\n")
        lines.append("\n")

    lines.append("## Your Task\n")
    lines.append("Generate **5-10 initial abstraction predicates** that would help CEGAR get started.\n")
    lines.append("These are Boolean features for PredicateCPA precision tracking, NOT invariants.\n")
    lines.append("They do not need to be true everywhere — they just need to be useful features to track.\n")
    lines.append("\n")
    lines.append("### Focus On\n")
    lines.append("- Loop counter bounds (e.g., `(bvsge i (_ bv0 32))`, `(bvslt i (_ bv100 32))`)\n")
    lines.append("- Accumulator relations (e.g., `(= sum (bvmul i (_ bv2 32)))`)\n")
    lines.append("- Parity/modulo relations (e.g., `(= (bvurem x (_ bv2 32)) (_ bv0 32))`)\n")
    lines.append("- Branch condition relations\n")
    lines.append("- Variables appearing in the assertion\n")
    lines.append("\n")
    lines.append("### SMT-LIB2 BV Syntax\n")
    lines.append("Use 32-bit bitvector operations:\n")
    lines.append("- `=` for equality, `bvslt`/`bvsgt`/`bvsle`/`bvsge` for comparisons\n")
    lines.append("- `bvadd`/`bvmul`/`bvsub`/`bvurem` for arithmetic\n")
    lines.append("- Constants: `(_ bv5 32)` for integer 5\n")
    lines.append("\n")
    lines.append("### Variable Names (CRITICAL)\n")
    lines.append("Use ONLY source-level C variable names (e.g., `x`, `y`, `i`, `sum`).\n")
    lines.append("NEVER use CPAchecker internal names: `|main::x@2|`, `|main::i|`, `.def_*`.\n")
    lines.append("\n")
    lines.append("### Output Format\n")
    lines.append('Output ONLY a JSON object mapping CFA node numbers to predicate lists:\n')
    lines.append('```json\n')
    lines.append('{"N0": ["(= sum (bvmul i (_ bv2 32)))", "(bvsge i (_ bv0 32))", ...]}\n')
    lines.append('```\n')
    return "".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 bootstrap_build_prompt.py <benchmark.c|.i> [--output prompt.md]")
        sys.exit(1)

    bench = sys.argv[1]
    source = Path(bench).read_text()
    assertion = extract_assertion(source)
    prompt = build_prompt(source, assertion)

    output = None
    if len(sys.argv) > 3 and sys.argv[2] == "--output":
        output = sys.argv[3]

    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(prompt)
        print(f"Prompt written to {output} ({len(prompt)} chars)")
    else:
        print(prompt)


if __name__ == "__main__":
    main()
