#!/usr/bin/env python3
"""Diagnose batch evaluation results — produce richer CSV + JSON + failure analysis."""
import csv, json, os, re, sys
from collections import defaultdict

BATCH_DIR = sys.argv[1] if len(sys.argv) > 1 else "results/vguided-cegar/batch_20260528_clean"

def extract_assertion(source_path):
    """Extract assertion expression from C source."""
    if not os.path.exists(source_path):
        return "", [], set()
    try:
        text = open(source_path).read()
    except Exception:
        return "", [], set()
    keywords = {'int', 'unsigned', 'if', 'else', 'while', 'return', 'void', 'char', 'long', 'short',
                 'sizeof', 'extern', 'const', 'static', 'volatile', 'signed', 'double', 'float',
                 'true', 'false', 'NULL', 'ERROR', '__VERIFIER', 'reach_error', 'abort', 'cond'}
    # __VERIFIER_assert(expr); — find calls NOT definitions
    for m in re.finditer(r'__VERIFIER_assert\s*\(\s*(.+?)\s*\)\s*;', text):
        expr = m.group(1).strip().replace('\n', ' ').replace('\r', '')
        if 'cond' in expr and 'void' not in expr:
            continue
        vars_ = set(re.findall(r'\b([a-zA-Z_]\w*)\b', expr))
        vars_ -= keywords
        ops = {'==', '!=', '<', '<=', '>=', '>', '%', '+', '-', '*'} & set(expr)
        return expr, sorted(vars_), ops
    # if (!(expr)) { ERROR: ... }
    m = re.search(r'if\s*\(\s*!\s*\(\s*(.+?)\s*\)\s*\)\s*\{?\s*ERROR', text)
    if m:
        expr = m.group(1).strip().replace('\n', ' ').replace('\r', '')
        vars_ = set(re.findall(r'\b([a-zA-Z_]\w*)\b', expr))
        vars_ -= keywords
        return expr, sorted(vars_), {'==', '!=', '<', '<=', '>=', '>', '%', '+', '-', '*'} & set(expr)
    return "", [], set()

def extract_vfate(log_path):
    """Extract V-FATE predicates from log."""
    if not os.path.exists(log_path):
        return [], []
    entailed, abstraction = [], []
    try:
        for line in open(log_path, errors='replace'):
            if 'V-FATE' in line and 'ENTAILED:' in line:
                entailed.append(line.strip())
            elif 'V-FATE' in line and 'ABSTRACTION-CANDIDATE' in line:
                abstraction.append(line.strip())
    except Exception:
        pass
    return entailed, abstraction

def extract_llm_preds(log_path):
    """Extract LLM-generated predicates from log."""
    if not os.path.exists(log_path):
        return []
    preds = []
    try:
        for line in open(log_path, errors='replace'):
            if 'LLM:' in line and '->' in line and '[' in line:
                preds.append(line.strip())
    except Exception:
        pass
    return preds

def extract_injected(log_path):
    """Extract injected predicates from log."""
    if not os.path.exists(log_path):
        return 0, []
    count = 0
    preds = []
    try:
        for line in open(log_path, errors='replace'):
            if 'V one-shot precision injected' in line or 'V precision-injected' in line:
                count += 1
                preds.append(line.strip())
    except Exception:
        pass
    return count, preds

def category_reason(row):
    """Produce diagnosis reason."""
    stock_r = (row.get('stock_result') or '').strip()
    ent_r = (row.get('entailed_result') or row.get('result') or '').strip()
    prec_r = (row.get('precision_result') or row.get('result') or '').strip()
    try: srefs = int(row.get('stock_refs') or 0)
    except: srefs = 0
    try: erefs = int(row.get('entailed_refs') or 0)
    except: erefs = 0
    try: prefs = int(row.get('precision_refs') or 0)
    except: prefs = 0

    stock_solved = stock_r in ('TRUE', 'FALSE')
    stock_ok = stock_r in ('TRUE', 'FALSE', 'true', 'false', 'configuration')

    if not stock_ok:
        if ent_r in ('TRUE', 'FALSE'):
            return "stock-timeout-v-solved", f"stock {stock_r} timeout but entailed solved it"
        return "timeout-incomparable", f"stock result={stock_r}; cannot compare refinement reduction"
    if srefs < 10:
        return "too-easy", f"stock_refs={srefs}, no room for improvement"
    if prefs < erefs * 0.75:
        return "relational-positive", f"precision_refs={prefs} << entailed_refs={erefs}; precision injection helps"
    if erefs < srefs * 0.75 and prefs >= erefs * 0.9:
        return "bounds-dominated", f"entailed improved ({srefs}→{erefs}) but precision no further gain"
    if prefs > erefs * 1.5:
        return "regression", f"precision_refs={prefs} > entailed_refs={erefs}*1.5"
    return "no-effect", f"precision_refs={prefs} ≈ entailed_refs={erefs}; no significant change"

# --- Find candidate programs ---
candidates_file = os.path.join(BATCH_DIR, "..", "..", "..", "..", "tmp", "vg_candidates.txt")
# Actually read from the logs directory to find processed benchmarks
logs_dir = os.path.join(BATCH_DIR, "logs")
summary_csv = os.path.join(BATCH_DIR, "summary.csv")

if not os.path.exists(summary_csv):
    # Use stock_scan.csv if summary doesn't exist
    stock_csv = os.path.join(BATCH_DIR, "stock_scan.csv")
    if not os.path.exists(stock_csv):
        print(f"No CSV found in {BATCH_DIR}", file=sys.stderr)
        sys.exit(1)
    rows = list(csv.DictReader(open(stock_csv)))
else:
    rows = list(csv.DictReader(open(summary_csv)))

# Deduplicate by benchmark name
seen = set()
unique_rows = []
for r in rows:
    name = r.get('benchmark', '')
    if name and name not in seen:
        seen.add(name)
        unique_rows.append(r)
rows = unique_rows

# Merge stock results
stock_csv = os.path.join(BATCH_DIR, "stock_scan.csv")
stock_results = {}
if os.path.exists(stock_csv):
    for r in csv.DictReader(open(stock_csv)):
        name = r.get('benchmark', '')
        if name:
            stock_results[name] = r.get('result', '').strip()

for row in rows:
    name = row.get('benchmark', '')
    # Add stock_result from stock_scan
    row['stock_result'] = stock_results.get(name, row.get('stock_result', row.get('result', '')))
SV_BASE = "/home/swear01/sv-benchmarks-vguided/c"
TEST_BASE = "/home/swear01/cpachecker/test/programs"
path_map = {}
for d in ["loop-acceleration", "loop-invariants", "loop-crafted", "loops"]:
    for f in os.listdir(os.path.join(SV_BASE, d)) if os.path.exists(os.path.join(SV_BASE, d)) else []:
        name = os.path.basename(f)
        path_map[name] = os.path.join(SV_BASE, d, f)
for root, _, files in os.walk(TEST_BASE):
    for f in files:
        if f.endswith('.c') or f.endswith('.i'):
            path_map[f] = os.path.join(root, f)

# Enrich each row
diag_rows = []
interesting = defaultdict(list)

for row in rows:
    name = row.get('benchmark', '')
    cat = row.get('category', '')
    src = path_map.get(name, '')

    # Assertion
    expr, vars_, ops = extract_assertion(src)
    row['assertion_expr'] = expr
    row['assertion_vars'] = ' '.join(vars_)
    row['assertion_has_mod'] = '%' in ops or 'mod' in expr.lower()
    row['assertion_has_relation'] = bool({'==', '!=', '<', '<=', '>=', '>'} & ops)

    # LLM predicates
    entailed_log = os.path.join(logs_dir, f"{name}.entailed.log")
    precision_log = os.path.join(logs_dir, f"{name}.precision.log")
    llm = extract_llm_preds(entailed_log) or extract_llm_preds(precision_log)
    row['llm_predicate_lines'] = len(llm)
    row['llm_predicates_sample'] = '; '.join(llm[:3]) if llm else 'none'

    # V-FATE
    ent, abst = extract_vfate(precision_log) or extract_vfate(entailed_log)
    row['entailed_fate_count'] = len(ent)
    row['abstraction_fate_count'] = len(abst)
    row['top_abstraction'] = '; '.join(abst[:3]) if abst else 'none'

    # Injection
    inj_count, inj_preds = extract_injected(precision_log)
    row['precision_injected_events'] = inj_count

    # Category
    diag_cat, reason = category_reason(row)
    row['category'] = diag_cat
    row['diagnosis_reason'] = reason

    diag_rows.append(row)
    if diag_cat != 'too-easy':
        interesting[diag_cat].append(row)

# Write enriched CSV
out_csv = os.path.join(BATCH_DIR, "summary_enriched.csv")
fields = list(diag_rows[0].keys())
with open(out_csv, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
    w.writeheader()
    w.writerows(diag_rows)
print(f"Enriched CSV: {out_csv} ({len(diag_rows)} rows)")

# Write interesting cases report
report = os.path.join(BATCH_DIR, "interesting_cases.md")
with open(report, 'w') as f:
    f.write("# Interesting Cases Report\n\n")
    for cat_name, cat_rows in sorted(interesting.items()):
        f.write(f"## {cat_name} ({len(cat_rows)} cases)\n\n")
        f.write("| Benchmark | Stock | Entailed | Precision | Assertion | LLM Preds | Reason |\n")
        f.write("|-----------|-------|----------|-----------|-----------|-----------|--------|\n")
        for r in cat_rows:
            f.write(f"| {r['benchmark']} | {r.get('stock_refs','?')} | {r.get('entailed_refs','?')} | "
                    f"{r.get('precision_refs','?')} | {r.get('assertion_expr','?')[:40]} | "
                    f"{r.get('llm_predicate_lines','?')} | {r.get('diagnosis_reason','?')[:60]} |\n")
        f.write("\n")
    f.write("\n## Next Steps\n\n")
    if interesting.get('relational-positive'):
        f.write(f"- {len(interesting['relational-positive'])} relational-positive case(s) found\n")
    if interesting.get('bounds-dominated'):
        f.write(f"- {len(interesting['bounds-dominated'])} bounds-dominated cases:\n")
        for r in interesting['bounds-dominated'][:5]:
            f.write(f"  - {r['benchmark']}: {r.get('diagnosis_reason','')}\n")
    f.write("- Consider adding assertion-oracle baseline for cases with assertion relations\n")
    f.write("- For bounds-dominated cases: check if LLM generated relational predicates or only bounds\n")
    f.write("- For timeout-incomparable cases: increase timelimit or exclude from evaluation\n")

print(f"Report: {report}")

# Per-benchmark JSON
diag_dir = os.path.join(BATCH_DIR, "diagnostics")
os.makedirs(diag_dir, exist_ok=True)
for row in diag_rows:
    name = row['benchmark']
    json_path = os.path.join(diag_dir, f"{name}.json")
    diag = {k: str(v)[:200] for k, v in row.items()}
    with open(json_path, 'w') as f:
        json.dump(diag, f, indent=2)
print(f"Diagnostics: {diag_dir} ({len(diag_rows)} files)")
