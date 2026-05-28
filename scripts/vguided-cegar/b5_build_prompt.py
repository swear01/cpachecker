#!/usr/bin/env python3
"""B5 Phase 2: Build LLM repair prompt from benchmark + B5 context summaries.

Usage: python3 b5_build_prompt.py <benchmark.c> <b5_summary_dir> [--output prompt.md]
"""

import json
import os
import re
import sys
from pathlib import Path


def extract_assertion(source_code):
    """Extract assertion expression from C source, handling nested parens."""
    for m in re.finditer(r'__VERIFIER_assert\s*\(', source_code):
        start = m.end()
        depth = 1
        i = start
        while i < len(source_code) and depth > 0:
            if source_code[i] == '(':
                depth += 1
            elif source_code[i] == ')':
                depth -= 1
            i += 1
        if depth != 0:
            continue
        expr = source_code[start:i-1].strip()
        # Skip function definitions
        if re.match(r'^(int|unsigned|long|char|void|short|float|double|bool|_Bool)\s+\w+\s*$', expr):
            continue
        return expr
    return ""


def build_prompt(benchmark_path, summary_dir):
    source = Path(benchmark_path).read_text()
    assertion = extract_assertion(source)

    # Read all refinement summaries
    summary_dir = Path(summary_dir)
    md_files = sorted(summary_dir.glob("refinement_*.md"))
    if not md_files:
        raise FileNotFoundError(f"No refinement_*.md files in {summary_dir}")

    sections = []

    # --- HEADER ---
    sections.append(f"# B5 Predicate Repair Request\n")
    sections.append(f"Benchmark: `{os.path.basename(benchmark_path)}`\n")
    sections.append(f"\n")

    # --- SOURCE CODE ---
    sections.append("## Source Code\n")
    sections.append("```c\n")
    sections.append(source.rstrip())
    sections.append("\n```\n\n")

    # --- ASSERTION ---
    sections.append("## Target Assertion\n")
    if assertion:
        sections.append(f"```c\n__VERIFIER_assert({assertion});\n```\n")
        vars_ = list(set(re.findall(r'\b([a-zA-Z_]\w*)\b', assertion)))
        sections.append(f"Assertion variables: {', '.join(vars_)}\n")
    else:
        sections.append("Not found in source.\n")
    sections.append("\n")

    # --- CEGAR CONTEXT ---
    sections.append("## CEGAR Failure Context\n")
    sections.append(f"The following sections show context from {len(md_files)} CEGAR refinements.\n")
    sections.append("Each refinement represents one spurious counterexample that CPAchecker failed to rule out.\n")
    sections.append("\n")

    for mdf in md_files:
        content = mdf.read_text()
        # Strip the outer H1 header and adjust titles
        content = re.sub(r'^# B5 CEGAR Context.*\n', '', content)
        sections.append(content)
        sections.append("\n---\n\n")

    # --- REPAIR TASK ---
    sections.append("## Repair Task\n\n")
    sections.append("You are analyzing a CPAchecker CEGAR run that is stuck on the benchmark above.\n")
    sections.append(f"The verifier produced {len(md_files)} spurious counterexample traces before timing out.\n\n")

    sections.append("### Step 1: Identify the Interpolant Gap\n\n")
    sections.append("Before generating predicates, analyze what the current abstraction is missing:\n\n")
    sections.append("1. **What do the current interpolants already express?**\n")
    sections.append("   Look at the Interpolant sections in each refinement above.\n")
    sections.append("   List the key atoms the interpolant encodes (e.g., \"x < 99\", \"sn == 0\", \"y%2 in {0,1}\").\n\n")
    sections.append("2. **What does the assertion require?**\n")
    sections.append(f"   The target assertion is: `__VERIFIER_assert({assertion})`\n")
    if assertion:
        vars_ = list(set(re.findall(r'\b([a-zA-Z_]\w*)\b', assertion)))
        sections.append(f"   Assertion variables: {', '.join(vars_)}\n")
    sections.append("\n")
    sections.append("3. **What relation is MISSING between the interpolants and the assertion?**\n")
    sections.append("   — If the assertion involves 2+ variables, does the interpolant track their relationship?\n")
    sections.append("   — If the loop has an accumulator (e.g., sn += 2*i), does the interpolant relate sn to i?\n")
    sections.append("   — Does the interpolant only track bounds (i < N) but miss the variable relationship?\n")
    sections.append("   — Identify the specific missing formula (e.g., \"sn = 2*i\", \"x%2 == y%2\").\n\n")
    sections.append("4. **Where in the trace should this predicate be tracked?**\n")
    sections.append("   Look at the CFA Path in each refinement above.\n")
    sections.append("   Identify the CFA node (loop head, loop exit, or assertion site) where the predicate\n")
    sections.append("   would be most useful as an abstraction feature.\n\n")

    sections.append("### Step 2: Generate Repair Predicates\n\n")
    sections.append("Now generate **abstraction predicates** that address the missing relation:\n\n")

    sections.append("### Rules\n\n")
    sections.append("1. **Not invariants.** These are abstraction features tracked by PredicateCPA's precision.\n")
    sections.append("   They don't need to be true everywhere.\n")
    sections.append("2. **Avoid already-entailed predicates** (shown in CANDIDATE FATES as ENTAILED).\n")
    sections.append("3. **Avoid duplicates** with predicates already in the current precision.\n")
    sections.append("4. **Prefer relational predicates** (2+ variables) that distinguish abstract states on the trace.\n")
    sections.append("5. **Prefer loop-counter / accumulator relations** (e.g., sum vs i, x vs y parity).\n")
    sections.append("6. **Focus on assertion variables.** The assertion is about: " +
                   (', '.join(list(set(re.findall(r'\b([a-zA-Z_]\w*)\b', assertion)))) if assertion else "?"))
    sections.append("\n")

    sections.append("### SMT-LIB2 BV Syntax\n\n")
    sections.append("Use 32-bit bitvector operations:\n")
    sections.append("- `=` for equality\n")
    sections.append("- `bvslt`, `bvsgt`, `bvsle`, `bvsge` for signed comparisons\n")
    sections.append("- `bvadd`, `bvmul`, `bvsub`, `bvurem` (modulo) for arithmetic\n")
    sections.append("- `#x...` for hex constants, e.g. `(_ bv5 32)` for 5\n\n")
    sections.append("Examples:\n")
    sections.append("- `(= (bvurem x 2) (bvurem y 2))` — parity equality\n")
    sections.append("- `(= s (bvmul i (_ bv255 32)))` — accumulator relation\n")
    sections.append("- `(bvsge i (_ bv0 32))` — signed non-negative\n\n")

    sections.append("### Output Format\n\n")
    sections.append("Output ONLY a JSON object mapping CFA node numbers to predicate lists:\n\n")
    sections.append("```json\n")
    sections.append('{"N19": ["(= (bvurem x 2) (bvurem y 2))", "(bvsge i (_ bv0 32))"], ...}\n')
    sections.append("```\n")
    sections.append("\nUse node numbers from the trace (e.g., N19, N23).\n")

    return "".join(sections)


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 b5_build_prompt.py <benchmark.c> <b5_summary_dir> [--output prompt.md]")
        sys.exit(1)

    benchmark_path = sys.argv[1]
    summary_dir = sys.argv[2]
    output_file = None

    if len(sys.argv) > 3 and sys.argv[3] == "--output":
        output_file = sys.argv[4] if len(sys.argv) > 4 else None

    prompt = build_prompt(benchmark_path, summary_dir)

    if output_file:
        Path(output_file).parent.mkdir(parents=True, exist_ok=True)
        Path(output_file).write_text(prompt)
        print(f"Prompt written to {output_file}")
    else:
        print(prompt)

    print(f"  size: {len(prompt)} chars, ~{len(prompt)//4} tokens")


if __name__ == "__main__":
    main()
