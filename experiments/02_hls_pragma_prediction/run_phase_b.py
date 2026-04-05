#!/usr/bin/env python3
"""
HLS Phase B: Multi-method A/B test with PFS scoring.

Methods:
  A1: Zero-shot (baseline, already have results)
  A3: With HLS rules (already have results)
  A4: Few-shot RAG (retrieve similar kernel pragmas from ForgeHLS)
  A5: Iterative refinement (generate → score → feedback → refine)

Metrics:
  - Type Match Rate (existing)
  - PFS: Pragma Fidelity Score (parameter accuracy via log-distance)
  - ADRS: Distance to Pareto frontier (existing)
"""
import sys, os, json, time, re, random, gc, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(line_buffering=True)

from carboncode.llm import ollama

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                         'datasets', 'ForgeHLS', 'designs', 'data_of_designs_forgehls.json')

# 10 representative kernels for A/B test
TARGET_ALGOS = [
    'fir_filter', 'AES_Encrypt', 'des_encrypt', 'adpcm',
    'gemm_ncubed', 'stencil_stencil2d', 'dct', 'black_scholes',
    'median_filter', 'fft_strided',
]


def extract_code_text(source_code):
    if isinstance(source_code, list):
        return source_code[0].get('file_content', '') if source_code else ''
    return source_code


def extract_pragmas(code):
    return [l.strip() for l in code.split('\n') if '#pragma HLS' in l]


def parse_pragma_params(pragma):
    """Extract pragma type and numeric parameters."""
    params = {}
    if 'PIPELINE' in pragma:
        params['type'] = 'PIPELINE'
        m = re.search(r'II\s*=\s*(\d+)', pragma)
        params['II'] = int(m.group(1)) if m else None
        if 'OFF' in pragma:
            params['type'] = 'PIPELINE_OFF'
    elif 'UNROLL' in pragma:
        params['type'] = 'UNROLL'
        m = re.search(r'factor\s*=\s*(\d+)', pragma)
        params['factor'] = int(m.group(1)) if m else None
    elif 'ARRAY_PARTITION' in pragma or 'PARTITION' in pragma:
        params['type'] = 'PARTITION'
        m = re.search(r'factor\s*=\s*(\d+)', pragma)
        params['factor'] = int(m.group(1)) if m else None
        if 'complete' in pragma:
            params['partition_type'] = 'complete'
        elif 'cyclic' in pragma:
            params['partition_type'] = 'cyclic'
        elif 'block' in pragma:
            params['partition_type'] = 'block'
    return params


def compute_pfs(llm_pragmas, pareto_pragmas):
    """Pragma Fidelity Score: how close are the numeric parameters?"""
    llm_parsed = [parse_pragma_params(p) for p in llm_pragmas]
    par_parsed = [parse_pragma_params(p) for p in pareto_pragmas]

    if not par_parsed:
        return 1.0  # no pragmas to compare

    scores = []
    max_log = 5  # log2(32) = 5, reasonable max range

    # Match by type
    for pp in par_parsed:
        ptype = pp.get('type', '')
        # Find matching LLM pragma
        match = None
        for lp in llm_parsed:
            if lp.get('type', '') == ptype:
                match = lp
                break

        if match is None:
            scores.append(0.0)  # LLM missed this pragma type
            continue

        # Compare numeric parameters
        param_scores = []
        for key in ['II', 'factor']:
            if key in pp and pp[key] is not None and key in match and match[key] is not None:
                if pp[key] == 0 or match[key] == 0:
                    param_scores.append(1.0 if pp[key] == match[key] else 0.0)
                else:
                    log_dist = abs(math.log2(match[key] / pp[key]))
                    param_scores.append(max(0, 1.0 - log_dist / max_log))

        if param_scores:
            scores.append(sum(param_scores) / len(param_scores))
        else:
            scores.append(1.0)  # type matched, no numeric params to compare

    return sum(scores) / len(scores) if scores else 1.0


def load_all_target_algos():
    """Single-pass load of target algorithms."""
    import ijson
    target_set = set(TARGET_ALGOS)
    algo_data = {a: [] for a in TARGET_ALGOS}

    print("Loading ForgeHLS data (streaming)...")
    with open(DATA_FILE, 'rb') as f:
        for item in ijson.items(f, 'item'):
            aname = item.get('algo_name')
            if aname in target_set:
                algo_data[aname].append({
                    'Worst-caseLatency': item.get('Worst-caseLatency', 0),
                    'LUT': item.get('LUT', 0),
                    'DSP': item.get('DSP', 0),
                    'is_pareto': item.get('is_pareto', False),
                    'source_code': item.get('source_code', ''),
                })

    total = sum(len(v) for v in algo_data.values())
    print(f"  Loaded {total} entries")
    return algo_data


def find_similar_kernels(algo_data, target_algo, n=3):
    """Find n similar kernels from ForgeHLS for RAG context."""
    # Simple heuristic: pick other kernels with similar pragma count
    target_entries = algo_data.get(target_algo, [])
    if not target_entries:
        return []

    target_pareto = [d for d in target_entries if d.get('is_pareto')]
    if not target_pareto:
        return []

    best = min(target_pareto, key=lambda d: d.get('Worst-caseLatency', 1e18))
    best_code = extract_code_text(best.get('source_code', ''))
    target_pragma_count = len(extract_pragmas(best_code))

    examples = []
    for other_algo, entries in algo_data.items():
        if other_algo == target_algo or not entries:
            continue
        pareto = [d for d in entries if d.get('is_pareto')]
        if not pareto:
            continue
        other_best = min(pareto, key=lambda d: d.get('Worst-caseLatency', 1e18))
        other_code = extract_code_text(other_best.get('source_code', ''))
        other_pragmas = extract_pragmas(other_code)

        examples.append({
            'algo': other_algo,
            'latency': other_best['Worst-caseLatency'],
            'pragmas': other_pragmas[:5],  # limit context
        })

    # Sort by pragma count similarity
    examples.sort(key=lambda x: abs(len(x['pragmas']) - target_pragma_count))
    return examples[:n]


def merge_pragmas(original_code, llm_code):
    """Post-process merge: replace pragma lines only."""
    orig_lines = original_code.split('\n')
    llm_lines = llm_code.split('\n') if llm_code else []
    llm_pragmas = [l.strip() for l in llm_lines if '#pragma HLS' in l]

    pragma_positions = [i for i, line in enumerate(orig_lines) if '#pragma HLS' in line]

    merged = orig_lines.copy()
    for pos_idx, orig_pos in enumerate(pragma_positions):
        if pos_idx < len(llm_pragmas):
            indent = len(orig_lines[orig_pos]) - len(orig_lines[orig_pos].lstrip())
            merged[orig_pos] = ' ' * indent + llm_pragmas[pos_idx]

    if not pragma_positions and llm_pragmas:
        new_merged = []
        pragma_idx = 0
        for line in merged:
            stripped = line.lstrip()
            if pragma_idx < len(llm_pragmas) and stripped.startswith('for'):
                indent = len(line) - len(stripped)
                new_merged.append(' ' * indent + llm_pragmas[pragma_idx])
                pragma_idx += 1
            new_merged.append(line)
        merged = new_merged

    return '\n'.join(merged)


def run_method(code, algo_name, method, algo_data=None):
    """Run LLM with specified method."""

    if method == 'A1':
        prompt = f"""Optimize this HLS C code for minimum latency on Xilinx FPGA.
Focus on #pragma HLS directives: PIPELINE, UNROLL, ARRAY_PARTITION.
Resource budget: generous (80% LUT/DSP).

Algorithm: {algo_name}

```c
{code[:3000]}
```

Output the optimized code in a ```c``` block."""

    elif method == 'A3':
        prompt = f"""You are an HLS optimization expert. Optimize this code for minimum latency.

Important rules:
- PIPELINE II=1 on innermost loops for best throughput
- UNROLL factor should match data width (4, 8, 16)
- ARRAY_PARTITION complete for small arrays accessed in parallel
- ARRAY_PARTITION cyclic for large arrays with strided access

Algorithm: {algo_name}
Resource budget: 80% LUT/DSP.

```c
{code[:3000]}
```

Output optimized code in a ```c``` block."""

    elif method == 'A4':
        # Few-shot RAG
        examples = find_similar_kernels(algo_data, algo_name, n=3) if algo_data else []
        example_text = ""
        for ex in examples:
            pragma_str = '\n'.join(f'  {p}' for p in ex['pragmas'])
            example_text += f"\nExample: {ex['algo']} (best latency: {ex['latency']} cycles)\n{pragma_str}\n"

        prompt = f"""You are an HLS optimization expert. Optimize this code for minimum latency.

Here are optimal pragma configurations for similar algorithms:
{example_text}

Now optimize this algorithm: {algo_name}
Resource budget: 80% LUT/DSP.

```c
{code[:3000]}
```

Based on the examples above, output the optimized code with best pragmas in a ```c``` block."""

    elif method == 'A5':
        # Iterative: first pass same as A1, refinement done separately
        prompt = f"""Optimize this HLS C code for minimum latency on Xilinx FPGA.
Focus on #pragma HLS directives: PIPELINE, UNROLL, ARRAY_PARTITION.
Be aggressive: use PIPELINE II=1, UNROLL factor=8 or 16, ARRAY_PARTITION complete where possible.
Resource budget: generous (80% LUT/DSP).

Algorithm: {algo_name}

```c
{code[:3000]}
```

Output the optimized code in a ```c``` block."""

    resp = ollama.call(prompt, model='qwen2.5-coder:7b', max_tokens=2048)
    llm_code = ollama.extract_code(resp, 'c') or ollama.extract_code(resp, 'cpp')
    return llm_code, resp


def evaluate_kernel(algo, entries, method, algo_data=None):
    """Full evaluation for one kernel with one method."""
    pareto = [d for d in entries if d.get('is_pareto')]
    worst = max(entries, key=lambda d: d.get('Worst-caseLatency', 0))
    best = min(pareto, key=lambda d: d.get('Worst-caseLatency', 1e18)) if pareto else worst

    code = extract_code_text(worst.get('source_code', ''))
    if not code or len(code) < 50:
        return None

    best_code = extract_code_text(best.get('source_code', ''))
    pareto_pragmas = extract_pragmas(best_code)

    # Run LLM
    llm_code, resp = run_method(code, algo, method, algo_data)
    if not llm_code:
        return {'algo': algo, 'method': method, 'success': False}

    merged = merge_pragmas(code, llm_code)
    llm_pragmas = extract_pragmas(merged)

    # Type match
    llm_types = set()
    par_types = set()
    for p in llm_pragmas:
        if 'PIPELINE' in p and 'OFF' not in p: llm_types.add('PIPELINE')
        if 'UNROLL' in p and 'factor=1' not in p: llm_types.add('UNROLL')
        if 'PARTITION' in p: llm_types.add('PARTITION')
    for p in pareto_pragmas:
        if 'PIPELINE' in p and 'OFF' not in p: par_types.add('PIPELINE')
        if 'UNROLL' in p and 'factor=1' not in p: par_types.add('UNROLL')
        if 'PARTITION' in p: par_types.add('PARTITION')

    all_types = par_types | {'PIPELINE', 'UNROLL', 'PARTITION'}
    type_match = sum(1 for t in all_types if (t in llm_types) == (t in par_types)) / len(all_types)

    # PFS
    pfs = compute_pfs(llm_pragmas, pareto_pragmas)

    return {
        'algo': algo,
        'method': method,
        'success': True,
        'type_match': round(type_match, 3),
        'pfs': round(pfs, 3),
        'llm_pragma_count': len(llm_pragmas),
        'pareto_pragma_count': len(pareto_pragmas),
        'llm_pragmas': llm_pragmas[:5],
        'pareto_pragmas': pareto_pragmas[:5],
    }


def main():
    random.seed(42)
    ts = int(time.time())

    methods = ['A1', 'A4']  # Start with baseline + RAG
    if len(sys.argv) > 1:
        methods = sys.argv[1].split(',')

    algo_data = load_all_target_algos()

    all_results = []

    for method in methods:
        print(f"\n{'='*70}")
        print(f"  Method: {method}")
        print(f"{'='*70}")

        method_results = []
        for i, algo in enumerate(TARGET_ALGOS):
            entries = algo_data.get(algo, [])
            if not entries:
                continue

            print(f"  [{i+1}/10] {algo}...", end=' ', flush=True)
            result = evaluate_kernel(algo, entries, method, algo_data)

            if result and result.get('success'):
                print(f"TypeMatch={result['type_match']:.0%} PFS={result['pfs']:.3f}")
                method_results.append(result)
            else:
                print("FAILED")
                if result:
                    method_results.append(result)

        all_results.extend(method_results)

        # Method summary
        ok = [r for r in method_results if r.get('success')]
        if ok:
            avg_type = sum(r['type_match'] for r in ok) / len(ok)
            avg_pfs = sum(r['pfs'] for r in ok) / len(ok)
            print(f"\n  {method} Summary: TypeMatch={avg_type:.1%}, PFS={avg_pfs:.3f} (n={len(ok)})")

    # Save
    out_file = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                            'check', f'hls_phase_b_{ts}.json')
    with open(out_file, 'w') as f:
        json.dump({'timestamp': ts, 'methods': methods, 'results': all_results}, f, indent=2)
    print(f"\nSaved: {out_file}")


if __name__ == '__main__':
    main()
