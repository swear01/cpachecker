#!/usr/bin/env python3
"""Static target classifier for Bootstrap+B5-MR rescue candidates.

Usage: python3 classify_bootstrap_targets.py <benchmark.c|.i> [--json]
       python3 classify_bootstrap_targets.py --csv <candidates.csv> [--output out.csv]
"""

import json, re, sys, os
from pathlib import Path


def classify(source):
    features = extract_features(source)
    label, reason = apply_rules(features)
    features['classification'] = label
    features['reason'] = reason
    return features


def extract_features(source):
    f = {}
    f['has_array'] = bool(re.search(r'\[.*\]', source))
    f['has_malloc'] = bool(re.search(r'\b(malloc|calloc|realloc|free)\b', source))
    f['has_struct'] = bool(re.search(r'\b(struct|union)\b', source))
    f['has_float'] = bool(re.search(r'\b(float|double)\b', source))
    f['has_bitshift'] = bool(re.search(r'<<|>>', source))
    f['has_pthread'] = bool(re.search(r'\b(pthread|__VERIFIER_atomic)\b', source))

    # Pointer: -> arrow operator or explicit pointer declaration/variable
    # Avoid matching macro expansions in .i files (__attribute__, extern, etc.)
    f['has_pointer'] = '->' in source and bool(re.search(r'\w\s*->\s*\w', source))  # actual member access
    f['has_pointer'] = f['has_pointer'] or bool(re.search(r'\*\s*(ptr|p\b|q\b|r\b)', source))  # named pointer vars
    f['has_pointer'] = f['has_pointer'] or bool(re.search(r'malloc|calloc|free', source))  # heap allocation

    # assertion extraction
    assertion = ""
    for m in re.finditer(r'__VERIFIER_assert\s*\(', source):
        start = m.end(); depth = 1; i = start
        while i < len(source) and depth > 0:
            if source[i] == '(': depth += 1
            elif source[i] == ')': depth -= 1
            i += 1
        if depth == 0:
            expr = source[start:i-1].strip()
            if not re.match(r'^(int|unsigned|void|char|long|short|float|double)\s+\w+$', expr):
                assertion = expr; break

    f['assertion_mentions_array'] = '[' in assertion or ']' in assertion
    assertion_vars = set(re.findall(r'\b([a-zA-Z_]\w*)\b', assertion))

    # loops
    loops = re.findall(r'\b(while|for)\s*\(', source)
    f['num_loops'] = len(loops)

    # counter updates: i++, i--, ++i, --i, i +=, i -=
    counters = set(re.findall(r'\b(\w+)\s*(\+\+|--|\\+\+|\--)\b', source))
    counters |= set(re.findall(r'\b(\w+)\s*\+=\s*\d+', source))
    counters |= set(re.findall(r'\b(\w+)\s*-=\s*\d+', source))
    f['has_counter'] = len(counters) > 0

    # accumulator: s += expr where expr contains another variable
    acc = re.findall(r'(\w+)\s*\+=\s*\w+\s*[*]\s*\w+|\b(\w+)\s*=\s*\w+\s*\+\s*\w+', source)
    f['has_accumulator'] = bool(acc)

    # assertion overlaps with loop/counter vars
    f['assertion_vars'] = list(assertion_vars)[:10]
    f['assertion_mentions_loop_vars'] = bool(assertion_vars & (counters | set(re.findall(r'\b(i|j|k|n|x|y|s|sum|sn)\b', source))))

    f['likely_cross_loop'] = f['num_loops'] >= 2 and f['assertion_mentions_loop_vars']

    return f


def apply_rules(f):
    # SKIP severe cases
    if f['has_malloc']: return 'SKIP_POINTER_HEAP', 'malloc/free detected'
    if f['has_struct']: return 'SKIP_POINTER_HEAP', 'struct/union detected'
    if f['has_float']: return 'SKIP_UNSUPPORTED_THEORY', 'float/double'
    if f['has_pthread']: return 'SKIP_UNSUPPORTED_THEORY', 'pthread/concurrency'

    # RUN_SCALAR
    if not f['has_array'] and not f['has_pointer']:
        if f['num_loops'] >= 1:
            if f['likely_cross_loop']:
                return 'RUN_SCALAR', 'scalar, multi-loop, counter/accumulator, assertion-loop relation'
            if f['assertion_mentions_loop_vars']:
                return 'RUN_SCALAR', 'scalar, loop-counter, assertion-loop relation'
            return 'RUN_SCALAR', 'scalar loop with counters'
        return 'SKIP_ARRAY_CONTENT', 'no loops detected'

    # RUN_ARRAY_SCALAR
    if f['has_array'] and not f['assertion_mentions_array'] and not f['has_pointer']:
        if f['num_loops'] >= 1 and f['assertion_mentions_loop_vars']:
            return 'RUN_ARRAY_SCALAR', 'array present but likely scalar index/counter bottleneck'

    # RUN_ARRAY_SELECT_EXPERIMENTAL
    if f['has_array'] and f['assertion_mentions_array'] and not f['has_pointer']:
        return 'RUN_ARRAY_SELECT_EXPERIMENTAL', 'array in assertion, may need select support'

    # Parser risk
    if f['has_bitshift']: return 'PARSER_RISK', 'bitwise shifts may need bvshl'
    if f['has_pointer']: return 'PARSER_RISK', 'pointer syntax detected'

    return 'UNKNOWN', 'no clear classification'


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 classify_bootstrap_targets.py <file|--csv candidates.csv>")
        sys.exit(1)

    if sys.argv[1] == '--csv':
        # Batch mode
        csv_in = sys.argv[2]
        csv_out = sys.argv[4] if len(sys.argv) > 3 and sys.argv[3] == '--output' else None
        import csv
        results = []
        with open(csv_in) as f:
            for row in csv.DictReader(f):
                path = row.get('local_path', row.get('input_file', ''))
                task = row.get('task', row.get('benchmark', ''))
                if not path or not os.path.exists(path):
                    results.append({**row, 'classification': 'SOURCE_MISSING', 'reason': 'file not found'})
                    continue
                try:
                    source = Path(path).read_text()
                    feat = classify(source)
                    feat['task'] = task
                    results.append(feat)
                except:
                    results.append({**row, 'classification': 'WORKFLOW_FAIL', 'reason': 'read error'})

        if results:
            fieldnames = list(results[0].keys())
            out_file = open(csv_out, 'w') if csv_out else sys.stdout
            w = csv.DictWriter(out_file, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(results)
            if csv_out:
                print(f"Written to {csv_out} ({len(results)} rows)")
                # Summary counts
                counts = {}
                for r in results:
                    c = r.get('classification', '?')
                    counts[c] = counts.get(c, 0) + 1
                print("Classification counts:")
                for k, v in sorted(counts.items(), key=lambda x: -x[1]):
                    print(f"  {k}: {v}")
    else:
        # Single file mode
        source = Path(sys.argv[1]).read_text()
        feat = classify(source)
        if '--json' in sys.argv:
            print(json.dumps(feat, indent=2))
        else:
            print(f"Classification: {feat['classification']}")
            print(f"Reason: {feat['reason']}")
            for k, v in feat.items():
                if k not in ('classification', 'reason'):
                    print(f"  {k}: {v}")


if __name__ == '__main__':
    main()
