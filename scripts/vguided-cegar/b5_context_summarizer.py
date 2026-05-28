#!/usr/bin/env python3
"""B5 context summarizer: converts raw B5 dump JSON to compact LLM-readable Markdown."""

import json
import os
import re
import sys
from collections import OrderedDict
from pathlib import Path

def clean_variable_name(encoded_name):
    """Convert |main::sn@2| -> sn@2, map to simple name sn."""
    m = re.search(r'\|?([^|]+)::([^@]+)(@\d+)?\|?', encoded_name)
    if m:
        cname = m.group(2)
        idx = m.group(3) or ''
        return f"{cname}{idx}"
    return encoded_name

def extract_simple_atoms(smt_text):
    """Extract simple comparison atoms from SMT-LIB2 dump."""
    atoms = []
    patterns = [
        (r'\(=\s+\|?[^)]+\s+\(_\s+bv\d+\s+(\d+)\)\)', '= {}'),
        (r'\(bvslt\s+\|?([^)]+)\s+\(_\s+bv\d+\s+(\d+)\)\)', '{} < {}'),
        (r'\(bvsgt\s+\|?([^)]+)\s+\(_\s+bv\d+\s+(\d+)\)\)', '{} > {}'),
        (r'\(bvsle\s+\|?([^)]+)\s+\(_\s+bv\d+\s+(\d+)\)\)', '{} <= {}'),
        (r'\(bvsge\s+\|?([^)]+)\s+\(_\s+bv\d+\s+(\d+)\)\)', '{} >= {}'),
        (r'\(bvule\s+\|?([^)]+)\s+\(_\s+bv\d+\s+(\d+)\)\)', '{} u<= {}'),
        (r'\(bvugt\s+\|?([^)]+)\s+\(_\s+bv\d+\s+(\d+)\)\)', '{} u> {}'),
    ]
    for pattern, template in patterns:
        for match in re.finditer(pattern, smt_text):
            raw = match.group(0).strip()
            atoms.append(raw)
    return atoms[:8]

def extract_variables(smt_text):
    """Extract variable names from SMT-LIB2 declare-fun."""
    vars_enc = set(re.findall(r'declare-fun\s+\|?([^|\s]+::[^|]+)\|?\s', smt_text))
    vars_simple = re.findall(r'declare-fun\s+\|?([^|]+)::([^@]+)(@\d+)?\|?\s', smt_text)
    result = {}
    for full_match in vars_enc:
        cm = re.match(r'([^:]+)::([^@]+)(@\d+)?', full_match)
        if cm:
            result[cm.group(2)] = f"|{full_match}|"
    return result

def count_assertions(smt_text):
    return len(re.findall(r'\(assert\s', smt_text))

def pretty_branch_condition(edge):
    """Convert edge branch info to readable string."""
    cond = edge.get('branch_condition', '')
    truth = edge.get('branch_truth', None)
    if not cond:
        return edge.get('edge_code', '')
    code = edge.get('edge_code', '')
    if truth is not None:
        return f"{code} [truth_assumption={truth}]"
    return code

def summarize_trace(d):
    """Summarize trace locations and edges."""
    lines = []
    lines.append("## Trace Summary")
    lines.append("")
    lines.append(f"- **Locations**: {len(d.get('trace_locations', []))} CFA nodes")
    lines.append(f"- **Edges**: {len(d.get('cfa_edges', []))} CFA edges")
    lines.append("")

    # Build trace path
    lines.append("### CFA Path")
    lines.append("")
    edges = d.get('cfa_edges', [])
    for i, edge in enumerate(edges):
        node = edge.get('node', '?')
        etype = edge.get('edge_type', '?')
        code = edge.get('edge_code', '')
        eline = edge.get('edge_line', '?')
        parts = [f"  {i+1}. {node} (line {eline})"]
        if etype == 'AssumeEdge':
            branch_str = pretty_branch_condition(edge)
            parts.append(f" → `{branch_str}`")
        elif code:
            parts.append(f" → `{code}`")
        else:
            parts.append(f" [{etype}]")
        lines.append("".join(parts))
    lines.append("")

    # Branch conditions summary
    branches = [e for e in edges if e.get('edge_type') == 'AssumeEdge']
    if branches:
        lines.append("### Branch Conditions")
        lines.append("")
        lines.append("| Node | Line | Condition | Truth Assumption |")
        lines.append("|------|------|-----------|-----------------|")
        for b in branches:
            node = b.get('node', '?')
            eline = b.get('edge_line', '?')
            code = b.get('edge_code', '')
            truth = b.get('branch_truth', '?')
            lines.append(f"| {node} | {eline} | `{code}` | {truth} |")
        lines.append("")
    return "".join(l + "\n" for l in lines)

def summarize_block_formulas(d):
    """Summarize block formulas without full dump."""
    lines = []
    lines.append("## Block Formulas")
    lines.append("")
    bf_list = d.get('block_formulas', [])
    for bf in bf_list:
        idx = bf['index']
        smt = bf['smt']
        n_assert = count_assertions(smt)
        length = len(smt)
        variables = extract_variables(smt)
        var_names = ", ".join(variables.keys()) if variables else "none"
        lines.append(f"### Block [{idx}] ({length} chars, {n_assert} assertions)")
        lines.append(f"- Variables: {var_names}")
        lines.append(f"- SSA aliases: {', '.join(f'{k}={variables[k]}' for k in list(variables.keys())[:10])}")
        lines.append("")
    return "".join(l + "\n" for l in lines)

def summarize_interpolants(d):
    """Summarize interpolants with simplification."""
    lines = []
    lines.append("## Interpolants")
    lines.append("")
    itp_list = d.get('interpolants', [])
    if not itp_list:
        lines.append("No interpolants available (trace was feasible).")
        lines.append("")
        return "".join(l + "\n" for l in lines)

    for itp in itp_list:
        idx = itp['index']
        smt = itp['smt']
        variables = extract_variables(smt)
        atoms = extract_simple_atoms(smt)
        n_assert = count_assertions(smt)
        length = len(smt)

        lines.append(f"### Interpolant [{idx}] ({length} chars, {n_assert} assertions)")
        lines.append("")
        var_names = ", ".join(variables.keys()) if variables else "none"
        lines.append(f"- Variables: {var_names}")
        lines.append(f"- SSA aliases: {', '.join(f'{k}={variables[k]}' for k in list(variables.keys())[:10])}")
        if atoms:
            lines.append("- Simple atoms detected:")
            for a in atoms:
                simplified = a
                for k, v in variables.items():
                    simplified = simplified.replace(v, k)
                lines.append(f"  - `{simplified}`")
            lines.append("")
        else:
            lines.append("- No simple comparison atoms detected (complex formula)")
            lines.append("")

        lines.append("<details><summary>Raw SMT-LIB2</summary>")
        lines.append("")
        lines.append("```smt")
        lines.append(smt[:2000])
        if len(smt) > 2000:
            lines.append(f"... ({length - 2000} more chars)")
        lines.append("```")
        lines.append("")
        lines.append("</details>")
        lines.append("")
    return "".join(l + "\n" for l in lines)

def summarize_precision(d):
    """Summarize current predicate precision."""
    lines = []
    lines.append("## Current Precision")
    lines.append("")
    prec = d.get('precision', {})
    if prec is None:
        lines.append("Precision not available.")
        lines.append("")
        return "".join(l + "\n" for l in lines)

    global_count = prec.get('global_count', 0)
    preds = prec.get('global_predicates', [])
    lines.append(f"- Global predicates: {global_count}")
    lines.append("")
    if preds:
        for i, p in enumerate(preds[:10]):
            smt = p.get('smt', '')
            variables = extract_variables(smt)
            atoms = extract_simple_atoms(smt)
            var_names = ", ".join(variables.keys()) if variables else "?"
            lines.append(f"  {i+1}. ({', '.join(var_names)})")
            if atoms:
                lines.append(f"     `{atoms[0][:120]}`")
            else:
                lines.append(f"     `{smt[:120]}...`")
            lines.append("")
    else:
        lines.append("  No global predicates yet.")
        lines.append("")
    return "".join(l + "\n" for l in lines)

def summarize_candidate_fates(d):
    """Summarize LLM candidate classification."""
    lines = []
    lines.append("## LLM Candidate Fates")
    lines.append("")
    fates = d.get('candidate_fates', {})
    if fates is None:
        lines.append("Candidate fates not available.")
        lines.append("")
        return "".join(l + "\n" for l in lines)

    groups = [
        ('entailed', 'ENTAILED (blockFormula ⇒ p, already used to strengthen interpolant)'),
        ('abstraction_candidates', 'ABSTRACTION-CANDIDATE (not entailed, considered for precision injection)'),
        ('injected', 'INJECTED (actually inserted into precision)'),
    ]

    for key, desc in groups:
        count = fates.get(f"{key}_count", 0)
        items = fates.get(key, [])
        lines.append(f"### {key.replace('_', ' ').title()} ({count}) — {desc}")
        lines.append("")
        if items:
            for item in items[:8]:
                node = item.get('node', '?')
                smt = item.get('smt', '')
                variables = extract_variables(smt)
                atoms = extract_simple_atoms(smt)
                var_names = ", ".join(variables.keys()) if variables else "?"
                lines.append(f"- **{node}**: ({var_names})")
                if atoms:
                    for a in atoms[:2]:
                        simplified = a
                        for k, v in variables.items():
                            simplified = simplified.replace(v, k)
                        lines.append(f"    `{simplified}`")
                else:
                    lines.append(f"    `{smt[:150]}...`")
                lines.append("")
        else:
            lines.append("  None")
            lines.append("")
    return "".join(l + "\n" for l in lines)

def generate_repair_instructions(d, context):
    """Generate repair task instruction for LLM prompt context."""
    lines = []
    lines.append("## LLM Repair Instructions")
    lines.append("")
    lines.append("You are analyzing a spurious counterexample trace from CPAchecker's CEGAR loop.")
    lines.append("")

    # Context summary
    trace_ab_count = len(d.get('abstraction_states', []))
    bf_count = len(d.get('block_formulas', []))
    itp_count = len(d.get('interpolants', []))
    lines.append(f"- Abstraction states in trace: {trace_ab_count}")
    lines.append(f"- Block formulas (path constraints between abstractions): {bf_count}")
    lines.append(f"- Interpolants derived by CPAchecker: {itp_count}")

    fates = d.get('candidate_fates', {})
    entailed = fates.get('entailed_count', 0)
    candidates = fates.get('abstraction_candidates_count', 0)
    lines.append(f"- Entailed LLM predicates (strengthened interpolant): {entailed}")
    lines.append(f"- Abstraction-candidate LLM predicates (pending): {candidates}")
    lines.append("")

    lines.append("### Your Task")
    lines.append("")
    lines.append("Generate **abstraction predicates** that would help CPAchecker rule out this spurious trace." +
                 " These are Boolean features for precision tracking, not necessarily invariants.")
    lines.append("")
    lines.append("**Rules:**")
    lines.append("1. **Avoid already-entailed predicates.** They are already used (B1 path). Focus on new predicates.")
    lines.append("2. **Avoid duplicates.** Do not repeat predicates already in the current precision.")
    lines.append("3. **Prefer relational predicates** with 2+ variables that distinguish states on this trace.")
    lines.append("4. **Prefer loop-counter/accumulator relations** (e.g., sum vs i, x vs y across iterations).")
    lines.append("5. **Use SMT-LIB2 BV syntax**: `(= (bvurem x 2) (bvurem y 2))`, `(= s (* i 255))`," +
                 " `(>= i 0)`, `(bvslt x (bvadd y y))`.")
    lines.append("6. **Group predicates by CFA node** (use node numbers like N23, N19).")
    lines.append("7. **Output JSON**: `{\"N<node>\": [\"(pred1)\", \"(pred2)\", ...]}`")
    lines.append("")

    # Current precision info
    prec = d.get('precision', {})
    global_count = prec.get('global_count', 0) if prec else 0
    if global_count > 0:
        preds = prec.get('global_predicates', [])[:5]
        lines.append("**Do NOT regenerate these (already in precision):**")
        for p in preds:
            smt = p.get('smt', '')
            variables = extract_variables(smt)
            atoms = extract_simple_atoms(smt)
            if atoms:
                lines.append(f"- `{atoms[0][:120]}`")
            else:
                lines.append(f"- `{smt[:120]}...`")
        lines.append("")

    return "".join(l + "\n" for l in lines)

def summarize(json_path, output_path):
    """Main summarizer: convert one JSON dump to Markdown."""
    with open(json_path) as f:
        d = json.load(f)

    ref_idx = d.get('refinement_index', '?')
    sections = []

    sections.append(f"# B5 CEGAR Context — Refinement {ref_idx}\n")
    sections.append(f"\nStatus: {d.get('verification_status', 'unknown')}\n")

    sections.append(summarize_trace(d))
    sections.append(summarize_interpolants(d))
    sections.append(summarize_block_formulas(d))
    sections.append(summarize_precision(d))
    sections.append(summarize_candidate_fates(d))
    sections.append(generate_repair_instructions(d, {}))
    sections.append(f"---\n")
    sections.append(f"_Generated from {os.path.basename(json_path)}_\n")

    content = "".join(sections)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(content)
    return content

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 b5_context_summarizer.py <dump_dir> [<dump_dir> ...]")
        sys.exit(1)

    for dump_dir in sys.argv[1:]:
        dump_path = Path(dump_dir)
        if not dump_path.is_dir():
            print(f"Not a directory: {dump_dir}")
            continue

        json_files = sorted(dump_path.glob("refinement_*.json"))
        for jf in json_files:
            out_file = jf.with_suffix(".md")
            summary = summarize(str(jf), str(out_file))
            size = len(summary)
            lines = summary.count('\n')
            print(f"  {jf.name} → {out_file.name} ({lines} lines, {size} chars)")
        print(f"Done: {dump_dir}")

if __name__ == "__main__":
    main()
