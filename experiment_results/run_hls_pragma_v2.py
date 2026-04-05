#!/usr/bin/env python3
"""
HLS Pragma Optimization v2: Post-process merge approach.
Let 7B generate freely, then programmatically extract ONLY pragma lines
and merge them back into the original code. Guarantees 100% code preservation.
"""
import sys, os, json, time, re
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
]


def extract_code_text(source_code):
    if isinstance(source_code, list):
        return source_code[0].get('file_content', '') if source_code else ''
    return source_code


def merge_pragmas(original_code, llm_code):
    """
    Post-process merge: take pragma lines from LLM output,
    put them back into the original code structure.
    Guarantees 100% code preservation.
    """
    orig_lines = original_code.split('\n')
    llm_lines = llm_code.split('\n') if llm_code else []

    # Extract pragma lines from LLM output (in order)
    llm_pragmas = [l.strip() for l in llm_lines if '#pragma HLS' in l]

    # Find pragma positions in original code
    pragma_positions = []
    for i, line in enumerate(orig_lines):
        if '#pragma HLS' in line:
            pragma_positions.append(i)

    # Replace original pragmas with LLM pragmas (1:1 mapping)
    merged = orig_lines.copy()
    for pos_idx, orig_pos in enumerate(pragma_positions):
        if pos_idx < len(llm_pragmas):
            # Preserve original indentation
            indent = len(orig_lines[orig_pos]) - len(orig_lines[orig_pos].lstrip())
            merged[orig_pos] = ' ' * indent + llm_pragmas[pos_idx]

    # If LLM produced MORE pragmas than original, append extras near loops
    # (simplified: just note it, don't insert randomly)
    extra_pragmas = llm_pragmas[len(pragma_positions):]

    return '\n'.join(merged), len(extra_pragmas)


def optimize_and_merge(code, algo_name):
    """Ask 7B to optimize, then merge only pragmas back."""
    prompt = f"""Optimize this HLS C code for minimum latency on Xilinx FPGA.
Focus on #pragma HLS directives: use PIPELINE, UNROLL, ARRAY_PARTITION aggressively.
Resource budget: generous (80% LUT/DSP available).

Algorithm: {algo_name}

```c
{code[:3000]}
```

Output the optimized code in a ```c``` block."""

    resp = ollama.call(prompt, model='qwen2.5-coder:7b', max_tokens=2048)
    llm_code = ollama.extract_code(resp, 'c') or ollama.extract_code(resp, 'cpp')

    if not llm_code:
        return None, resp, 0

    # Post-process: merge ONLY pragmas
    merged, extra = merge_pragmas(code, llm_code)
    return merged, resp, extra


def main():
    print("Loading ForgeHLS data...")
    with open(DATA_FILE) as f:
        data = json.load(f)

    results = []
    ts = int(time.time())

    for algo in TARGET_ALGOS:
        print(f"\n{'='*60}")
        print(f"  {algo}")

        entries = [d for d in data if d.get('algo_name') == algo]
        if not entries:
            continue

        # Get worst and Pareto best
        pareto = [d for d in entries if d.get('is_pareto')]
        worst = max(entries, key=lambda d: d.get('Worst-caseLatency', 0))
        best = min(pareto, key=lambda d: d.get('Worst-caseLatency', 1e18)) if pareto else worst

        worst_lat = worst.get('Worst-caseLatency', 0)
        best_lat = best.get('Worst-caseLatency', 0)
        code = extract_code_text(worst.get('source_code', ''))
        if not code or len(code) < 50:
            continue

        print(f"  Worst: Lat={worst_lat} | Best: Lat={best_lat} | Gap: {worst_lat/max(best_lat,1):.0f}x")

        # Optimize with post-process merge
        merged_code, resp, extra_pragmas = optimize_and_merge(code, algo)

        if not merged_code:
            print(f"  ❌ No output")
            results.append({'algo': algo, 'success': False})
            continue

        # Verify 100% code preservation
        orig_non_pragma = [l.strip() for l in code.split('\n') if l.strip() and '#pragma' not in l]
        merged_non_pragma = [l.strip() for l in merged_code.split('\n') if l.strip() and '#pragma' not in l]
        preserved = orig_non_pragma == merged_non_pragma

        # Extract pragmas for comparison
        orig_pragmas = [l.strip() for l in code.split('\n') if '#pragma HLS' in l]
        merged_pragmas = [l.strip() for l in merged_code.split('\n') if '#pragma HLS' in l]
        best_pragmas = [l.strip() for l in extract_code_text(best.get('source_code', '')).split('\n') if '#pragma HLS' in l]

        # Score pragma quality
        has_pipeline = any('PIPELINE' in p and 'OFF' not in p for p in merged_pragmas)
        has_unroll_good = any('UNROLL' in p and 'factor=1' not in p for p in merged_pragmas)
        orig_had_pipeline_off = any('PIPELINE OFF' in p for p in orig_pragmas)
        changed_pipeline = orig_had_pipeline_off and has_pipeline

        print(f"  Code preserved: {'✅ 100%' if preserved else '❌'}")
        print(f"  Pragmas: {len(orig_pragmas)} → {len(merged_pragmas)} (extra: {extra_pragmas})")
        print(f"  PIPELINE activated: {'✅' if changed_pipeline else '➡️ (already on or N/A)'}")
        print(f"  Good UNROLL: {'✅' if has_unroll_good else '❌'}")

        # Show pragma changes
        changed = 0
        for i, (o, m) in enumerate(zip(orig_pragmas, merged_pragmas)):
            if o != m:
                changed += 1
                if changed <= 3:
                    print(f"    {o}")
                    print(f"    → {m}")

        print(f"  Pragmas changed: {changed}/{len(orig_pragmas)}")

        results.append({
            'algo': algo, 'success': True, 'preserved': preserved,
            'worst_latency': worst_lat, 'best_latency': best_lat,
            'latency_gap': worst_lat / max(best_lat, 1),
            'pragmas_changed': changed, 'total_pragmas': len(orig_pragmas),
            'has_pipeline': has_pipeline, 'has_unroll': has_unroll_good,
            'activated_pipeline': changed_pipeline,
        })

    # Summary
    print(f"\n{'='*60}")
    print(f"  HLS Pragma v2 (Post-Process Merge) Results")
    print(f"{'='*60}")

    ok = [r for r in results if r.get('success')]
    n = len(ok)
    preserved = sum(1 for r in ok if r.get('preserved'))
    activated = sum(1 for r in ok if r.get('activated_pipeline'))
    unrolled = sum(1 for r in ok if r.get('has_unroll'))
    any_changed = sum(1 for r in ok if r.get('pragmas_changed', 0) > 0)

    print(f"  Kernels: {len(results)} total, {n} generated")
    print(f"  Code preserved: {preserved}/{n} ({100*preserved/max(n,1):.0f}%) ← should be 100% now")
    print(f"  Activated PIPELINE: {activated}/{n} ({100*activated/max(n,1):.0f}%)")
    print(f"  Good UNROLL: {unrolled}/{n} ({100*unrolled/max(n,1):.0f}%)")
    print(f"  Any pragma changed: {any_changed}/{n} ({100*any_changed/max(n,1):.0f}%)")

    out_file = os.path.join(os.path.dirname(__file__), '..', '..', '..',
                            'check', f'hls_pragma_v2_{ts}.json')
    with open(out_file, 'w') as f:
        json.dump({'results': results}, f, indent=2)
    print(f"  Saved: {out_file}")


if __name__ == '__main__':
    main()
