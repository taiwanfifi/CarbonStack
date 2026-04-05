#!/usr/bin/env python3
"""
HLS Phase A Experiment: LLM Pragma Prediction vs ForgeHLS Pareto Frontier
Memory-efficient: loads only target algo entries, not entire 968MB dataset.

Metrics:
1. Pragma Match Rate: % of pragma types correctly identified
2. ADRS: Average Distance to Reference Set (Pareto frontier)
3. Synthesizable Rate: pragma configs that match known-valid ForgeHLS entries

Baselines:
- Random pragma: random PIPELINE/UNROLL/PARTITION settings
- Default (worst): Vivado HLS defaults (worst latency config)
- ForgeHLS median: median design
- ForgeHLS Pareto: ground truth target
"""
import sys, os, json, time, re, random, gc
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(line_buffering=True)

from carboncode.llm import ollama

DATA_FILE = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                         'datasets', 'ForgeHLS', 'designs', 'data_of_designs_forgehls.json')

TARGET_ALGOS = [
    'fir_filter', 'AES_Encrypt', 'viterbi', 'des_encrypt', 'adpcm',
    'gemm_ncubed', 'gemm_blocked', 'matrix_multiply', 'syrk', 'mvt',
    'stencil_stencil2d', 'jacobi-2d', 'fdtd-2d', 'heat-3d',
    'dct', 'black_scholes', 'kmeans_clustering', 'fft_strided',
    'median_filter', 'histogram_equalization',
    'chebyshev_filter', 'jacobi-1d', 'image_convolution', 'gaussian_blur',
    'wallace_tree_adder', 'public_key_acceleration', 'speech_recognition_processor',
    'neuron_chip_network_processor', 'option_pricing', 'mersenne_twister',
]


def load_algo_data(algo_name):
    """Memory-efficient: stream JSON and only keep entries for target algo."""
    entries = []
    # Use ijson for streaming if available, else load and filter immediately
    try:
        import ijson
        with open(DATA_FILE, 'rb') as f:
            for item in ijson.items(f, 'item'):
                if item.get('algo_name') == algo_name:
                    # Only keep needed fields to save memory
                    entries.append({
                        'Worst-caseLatency': item.get('Worst-caseLatency', 0),
                        'LUT': item.get('LUT', 0),
                        'DSP': item.get('DSP', 0),
                        'is_pareto': item.get('is_pareto', False),
                        'source_code': item.get('source_code', ''),
                        'pragma_number': item.get('pragma_number', 0),
                    })
        return entries
    except ImportError:
        pass

    # Fallback: load in chunks to manage memory better
    # Read file and parse, but immediately filter
    print(f"  Loading data for {algo_name} (no ijson, using full load)...")
    with open(DATA_FILE) as f:
        data = json.load(f)

    for item in data:
        if item.get('algo_name') == algo_name:
            entries.append({
                'Worst-caseLatency': item.get('Worst-caseLatency', 0),
                'LUT': item.get('LUT', 0),
                'DSP': item.get('DSP', 0),
                'is_pareto': item.get('is_pareto', False),
                'source_code': item.get('source_code', ''),
                'pragma_number': item.get('pragma_number', 0),
            })

    del data
    gc.collect()
    return entries


def load_all_target_algos():
    """Load all target algos in one pass to avoid reading 968MB file 30 times."""
    print("Loading ForgeHLS data (single pass, filtering 30 targets)...")
    target_set = set(TARGET_ALGOS)
    algo_data = {a: [] for a in TARGET_ALGOS}

    try:
        import ijson
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
                        'pragma_number': item.get('pragma_number', 0),
                    })
        print(f"  Loaded {sum(len(v) for v in algo_data.values())} entries via ijson streaming")
        return algo_data
    except ImportError:
        pass

    # Fallback: full load, filter, release
    print("  (ijson not available, doing full load + filter)")
    with open(DATA_FILE) as f:
        data = json.load(f)

    for item in data:
        aname = item.get('algo_name')
        if aname in target_set:
            algo_data[aname].append({
                'Worst-caseLatency': item.get('Worst-caseLatency', 0),
                'LUT': item.get('LUT', 0),
                'DSP': item.get('DSP', 0),
                'is_pareto': item.get('is_pareto', False),
                'source_code': item.get('source_code', ''),
                'pragma_number': item.get('pragma_number', 0),
            })

    del data
    gc.collect()
    total = sum(len(v) for v in algo_data.values())
    print(f"  Loaded {total} entries, released rest from memory")
    return algo_data


def extract_code_text(source_code):
    if isinstance(source_code, list):
        return source_code[0].get('file_content', '') if source_code else ''
    return source_code


def extract_pragmas(code):
    """Extract all #pragma HLS lines from code."""
    return [l.strip() for l in code.split('\n') if '#pragma HLS' in l]


def pragma_features(pragmas):
    """Extract pragma type features for comparison."""
    features = {
        'has_pipeline': False, 'has_pipeline_ii1': False,
        'has_unroll': False, 'unroll_factors': [],
        'has_partition': False, 'partition_types': [],
        'has_interface': False, 'total_pragmas': len(pragmas),
    }
    for p in pragmas:
        if 'PIPELINE' in p and 'OFF' not in p:
            features['has_pipeline'] = True
            if 'II=1' in p:
                features['has_pipeline_ii1'] = True
        if 'UNROLL' in p:
            features['has_unroll'] = True
            m = re.search(r'factor=(\d+)', p)
            if m:
                features['unroll_factors'].append(int(m.group(1)))
        if 'ARRAY_PARTITION' in p or 'PARTITION' in p:
            features['has_partition'] = True
            if 'complete' in p:
                features['partition_types'].append('complete')
            elif 'cyclic' in p:
                features['partition_types'].append('cyclic')
            elif 'block' in p:
                features['partition_types'].append('block')
        if 'INTERFACE' in p:
            features['has_interface'] = True
    return features


def pragma_match_rate(llm_features, pareto_features):
    """Compute what fraction of pragma types the LLM correctly identified."""
    checks = [
        ('pipeline', llm_features['has_pipeline'], pareto_features['has_pipeline']),
        ('unroll', llm_features['has_unroll'], pareto_features['has_unroll']),
        ('partition', llm_features['has_partition'], pareto_features['has_partition']),
    ]
    correct = sum(1 for _, llm, pareto in checks if llm == pareto)
    return correct / len(checks), {name: (llm == par) for name, llm, par in checks}


def compute_adrs(llm_latency, llm_lut, pareto_points):
    """
    ADRS: Average Distance to Reference Set.
    For each point in the LLM's predicted set, find the minimum distance
    to any Pareto point. Lower = better. 0 = on the frontier.

    We normalize by the range of the Pareto set.
    """
    if not pareto_points:
        return 1.0  # worst

    lat_range = max(p[0] for p in pareto_points) - min(p[0] for p in pareto_points)
    lut_range = max(p[1] for p in pareto_points) - min(p[1] for p in pareto_points)

    if lat_range == 0:
        lat_range = max(p[0] for p in pareto_points)
    if lut_range == 0:
        lut_range = max(p[1] for p in pareto_points)

    if lat_range == 0 or lut_range == 0:
        return 0.5  # can't compute

    min_dist = float('inf')
    for plat, plut in pareto_points:
        d = ((llm_latency - plat) / lat_range) ** 2 + ((llm_lut - plut) / lut_range) ** 2
        d = d ** 0.5
        if d < min_dist:
            min_dist = d

    return min_dist


def find_nearest_design(entries, pragma_signature):
    """Find the design in ForgeHLS whose pragma set most closely matches."""
    best_match = None
    best_overlap = -1

    llm_pragma_set = set(pragma_signature)

    for entry in entries:
        code = extract_code_text(entry.get('source_code', ''))
        entry_pragmas = set(extract_pragmas(code))

        overlap = len(llm_pragma_set & entry_pragmas)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match = entry

    return best_match, best_overlap


def merge_pragmas(original_code, llm_code):
    """Post-process merge: replace pragma lines only."""
    orig_lines = original_code.split('\n')
    llm_lines = llm_code.split('\n') if llm_code else []
    llm_pragmas = [l.strip() for l in llm_lines if '#pragma HLS' in l]

    pragma_positions = []
    for i, line in enumerate(orig_lines):
        if '#pragma HLS' in line:
            pragma_positions.append(i)

    merged = orig_lines.copy()
    for pos_idx, orig_pos in enumerate(pragma_positions):
        if pos_idx < len(llm_pragmas):
            indent = len(orig_lines[orig_pos]) - len(orig_lines[orig_pos].lstrip())
            merged[orig_pos] = ' ' * indent + llm_pragmas[pos_idx]

    # For zero-pragma originals, insert LLM pragmas before for-loops
    if not pragma_positions and llm_pragmas:
        new_merged = []
        pragma_idx = 0
        for line in merged:
            stripped = line.lstrip()
            if pragma_idx < len(llm_pragmas) and (stripped.startswith('for') or stripped.startswith('for(')):
                indent = len(line) - len(stripped)
                new_merged.append(' ' * indent + llm_pragmas[pragma_idx])
                pragma_idx += 1
            new_merged.append(line)
        merged = new_merged

    return '\n'.join(merged), len(llm_pragmas) - len(pragma_positions)


def generate_random_pragmas(num_pragmas):
    """Generate random pragma baseline."""
    pragmas = []
    types = ['PIPELINE', 'UNROLL', 'ARRAY_PARTITION']
    for _ in range(num_pragmas):
        t = random.choice(types)
        if t == 'PIPELINE':
            ii = random.choice([1, 2, 4])
            pragmas.append(f'#pragma HLS PIPELINE II={ii}')
        elif t == 'UNROLL':
            factor = random.choice([1, 2, 4, 8, 16])
            pragmas.append(f'#pragma HLS UNROLL factor={factor}')
        else:
            pragmas.append('#pragma HLS ARRAY_PARTITION variable=arr type=complete dim=1')
    return pragmas


def optimize_with_llm(code, algo_name, method='A1'):
    """Run LLM pragma optimization with different methods."""

    if method == 'A1':
        # Pragma-only prompt
        prompt = f"""You are an HLS optimization expert. Given this C code for {algo_name},
suggest optimal #pragma HLS directives for minimum latency on Xilinx FPGA.
Resource budget: generous (80% LUT/DSP available).

Focus ONLY on pragmas: PIPELINE (with II), UNROLL (with factor), ARRAY_PARTITION (type/dim/factor).

```c
{code[:3000]}
```

Output the optimized code with your pragma suggestions in a ```c``` block."""

    elif method == 'A3':
        # With ForgeHLS context
        prompt = f"""You are an HLS optimization expert. Given this C code for {algo_name},
suggest optimal #pragma HLS directives for minimum latency on Xilinx FPGA.

Important HLS optimization rules:
- PIPELINE II=1 on innermost loops gives best throughput
- UNROLL factor should match data width (4, 8, 16 common)
- ARRAY_PARTITION complete for small arrays accessed in parallel
- ARRAY_PARTITION cyclic for large arrays with strided access
- Too much UNROLL wastes DSP/LUT without latency benefit
- PIPELINE on outer loop + UNROLL inner is often optimal

Resource budget: generous (80% LUT/DSP available).

```c
{code[:3000]}
```

Output the optimized code in a ```c``` block."""

    resp = ollama.call(prompt, model='qwen2.5-coder:7b', max_tokens=2048)
    llm_code = ollama.extract_code(resp, 'c') or ollama.extract_code(resp, 'cpp')
    return llm_code, resp


def evaluate_kernel(algo, entries, method='A1'):
    """Full evaluation pipeline for one kernel."""
    pareto = [d for d in entries if d.get('is_pareto')]
    all_by_lat = sorted(entries, key=lambda d: d.get('Worst-caseLatency', 0))

    worst = max(entries, key=lambda d: d.get('Worst-caseLatency', 0))
    best = min(pareto, key=lambda d: d.get('Worst-caseLatency', 1e18)) if pareto else worst
    median_entry = all_by_lat[len(all_by_lat) // 2]

    worst_lat = worst.get('Worst-caseLatency', 0)
    worst_lut = worst.get('LUT', 0)
    best_lat = best.get('Worst-caseLatency', 0)
    best_lut = best.get('LUT', 0)
    median_lat = median_entry.get('Worst-caseLatency', 0)
    median_lut = median_entry.get('LUT', 0)

    code = extract_code_text(worst.get('source_code', ''))
    if not code or len(code) < 50:
        return None

    # Pareto frontier points for ADRS
    pareto_points = [(d['Worst-caseLatency'], d['LUT']) for d in pareto]

    # Get best (Pareto) pragmas for comparison
    best_code = extract_code_text(best.get('source_code', ''))
    pareto_pragmas = extract_pragmas(best_code)
    pareto_feat = pragma_features(pareto_pragmas)

    # --- LLM Optimization ---
    llm_code, llm_resp = optimize_with_llm(code, algo, method)
    if not llm_code:
        return {'algo': algo, 'success': False, 'error': 'no_output'}

    # Post-process merge
    merged_code, extra = merge_pragmas(code, llm_code)
    llm_pragmas = extract_pragmas(merged_code)
    llm_feat = pragma_features(llm_pragmas)

    # Find nearest ForgeHLS design to LLM's pragma config
    nearest, overlap = find_nearest_design(entries, llm_pragmas)
    llm_est_lat = nearest['Worst-caseLatency'] if nearest else worst_lat
    llm_est_lut = nearest['LUT'] if nearest else worst_lut

    # --- Random Baseline ---
    n_pragmas = max(len(pareto_pragmas), len(extract_pragmas(code)), 3)
    random_pragmas = generate_random_pragmas(n_pragmas)
    random_feat = pragma_features(random_pragmas)

    # --- Metrics ---
    # 1. Pragma Match Rate
    match_rate, match_details = pragma_match_rate(llm_feat, pareto_feat)
    random_match, _ = pragma_match_rate(random_feat, pareto_feat)

    # 2. ADRS
    llm_adrs = compute_adrs(llm_est_lat, llm_est_lut, pareto_points)
    worst_adrs = compute_adrs(worst_lat, worst_lut, pareto_points)
    median_adrs = compute_adrs(median_lat, median_lut, pareto_points)

    # 3. Percentile rank (what % of designs is LLM better than?)
    llm_percentile = sum(1 for d in entries if d['Worst-caseLatency'] >= llm_est_lat) / len(entries) * 100

    # Code preservation check
    orig_non_pragma = [l.strip() for l in code.split('\n') if l.strip() and '#pragma' not in l]
    merged_non_pragma = [l.strip() for l in merged_code.split('\n') if l.strip() and '#pragma' not in l]
    preserved = orig_non_pragma == merged_non_pragma

    result = {
        'algo': algo,
        'success': True,
        'preserved': preserved,
        'method': method,
        'num_designs': len(entries),
        'num_pareto': len(pareto),
        # Latency landscape
        'worst_latency': worst_lat,
        'best_latency': best_lat,
        'median_latency': median_lat,
        'latency_gap': worst_lat / max(best_lat, 1),
        # LLM results
        'llm_est_latency': llm_est_lat,
        'llm_pragmas': llm_pragmas,
        'llm_pragma_count': len(llm_pragmas),
        'llm_percentile': round(llm_percentile, 1),
        'llm_nearest_overlap': overlap,
        # Pragma match
        'pragma_match_rate': round(match_rate, 3),
        'pragma_match_details': match_details,
        'random_match_rate': round(random_match, 3),
        # ADRS
        'llm_adrs': round(llm_adrs, 4),
        'worst_adrs': round(worst_adrs, 4),
        'median_adrs': round(median_adrs, 4),
        # Features
        'llm_features': {k: v for k, v in llm_feat.items() if not isinstance(v, list)},
        'pareto_features': {k: v for k, v in pareto_feat.items() if not isinstance(v, list)},
    }
    return result


def main():
    random.seed(42)
    ts = int(time.time())

    # Single-pass load: memory efficient
    algo_data = load_all_target_algos()

    results = []
    method = 'A1'  # Default: pragma-only prompt

    if len(sys.argv) > 1:
        method = sys.argv[1]  # A1, A3

    print(f"\nMethod: {method}")
    print(f"Kernels: {len(TARGET_ALGOS)}")
    print("=" * 70)

    for i, algo in enumerate(TARGET_ALGOS):
        entries = algo_data.get(algo, [])
        if not entries:
            print(f"[{i+1}/30] {algo}: NO DATA")
            continue

        print(f"\n[{i+1}/30] {algo} ({len(entries)} designs)")

        result = evaluate_kernel(algo, entries, method)
        if not result:
            print(f"  ❌ Skipped (no code)")
            continue

        if not result.get('success'):
            print(f"  ❌ {result.get('error', 'unknown')}")
            results.append(result)
            continue

        print(f"  Preserved: {'✅' if result['preserved'] else '❌'}")
        print(f"  Pragma Match: {result['pragma_match_rate']*100:.0f}% (random: {result['random_match_rate']*100:.0f}%)")
        print(f"  ADRS: {result['llm_adrs']:.4f} (worst: {result['worst_adrs']:.4f}, median: {result['median_adrs']:.4f})")
        print(f"  Est Latency: {result['llm_est_latency']} (best: {result['best_latency']}, worst: {result['worst_latency']})")
        print(f"  Percentile: top {100 - result['llm_percentile']:.1f}% of designs")

        results.append(result)

        # Free memory for this algo's source code
        for entry in entries:
            entry.pop('source_code', None)

    # Release all data
    del algo_data
    gc.collect()

    # === Summary ===
    print(f"\n{'=' * 70}")
    print(f"  HLS Phase A Results — Method {method}")
    print(f"{'=' * 70}")

    ok = [r for r in results if r.get('success')]
    n = len(ok)

    if n == 0:
        print("  No successful results!")
        return

    preserved = sum(1 for r in ok if r.get('preserved'))
    avg_match = sum(r['pragma_match_rate'] for r in ok) / n
    avg_random = sum(r['random_match_rate'] for r in ok) / n
    avg_adrs = sum(r['llm_adrs'] for r in ok) / n
    avg_worst_adrs = sum(r['worst_adrs'] for r in ok) / n
    avg_median_adrs = sum(r['median_adrs'] for r in ok) / n
    avg_percentile = sum(r['llm_percentile'] for r in ok) / n

    # Pipeline identification rate
    pipeline_correct = sum(1 for r in ok
                           if r['llm_features']['has_pipeline'] == r['pareto_features']['has_pipeline'])

    print(f"\n  Kernels evaluated: {n}/30")
    print(f"  Code preserved: {preserved}/{n} ({100*preserved/n:.0f}%)")
    print(f"\n  --- Pragma Match Rate ---")
    print(f"  LLM avg: {avg_match*100:.1f}%")
    print(f"  Random avg: {avg_random*100:.1f}%")
    print(f"  Pipeline correct: {pipeline_correct}/{n} ({100*pipeline_correct/n:.0f}%)")

    print(f"\n  --- ADRS (lower = closer to Pareto) ---")
    print(f"  LLM: {avg_adrs:.4f}")
    print(f"  Worst: {avg_worst_adrs:.4f}")
    print(f"  Median: {avg_median_adrs:.4f}")

    print(f"\n  --- Percentile (higher = better) ---")
    print(f"  LLM avg: top {100 - avg_percentile:.1f}% of all designs")

    # Per-kernel summary table
    print(f"\n  {'Kernel':<30} {'Match%':>6} {'ADRS':>8} {'Pctile':>8} {'Gap':>8}")
    print(f"  {'-'*30} {'-'*6} {'-'*8} {'-'*8} {'-'*8}")
    for r in ok:
        pctile = f"top {100 - r['llm_percentile']:.0f}%"
        print(f"  {r['algo']:<30} {r['pragma_match_rate']*100:>5.0f}% {r['llm_adrs']:>8.4f} {pctile:>8} {r['latency_gap']:>7.0f}x")

    # Save results
    out = {
        'method': method,
        'timestamp': ts,
        'num_kernels': n,
        'summary': {
            'code_preserved': f"{preserved}/{n}",
            'avg_pragma_match': round(avg_match, 3),
            'avg_random_match': round(avg_random, 3),
            'avg_adrs_llm': round(avg_adrs, 4),
            'avg_adrs_worst': round(avg_worst_adrs, 4),
            'avg_adrs_median': round(avg_median_adrs, 4),
            'avg_percentile': round(avg_percentile, 1),
            'pipeline_correct_rate': round(pipeline_correct / n, 3),
        },
        'results': results,
    }

    out_file = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                            'check', f'hls_phase_a_{method}_{ts}.json')
    with open(out_file, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\n  Saved: {out_file}")


if __name__ == '__main__':
    main()
