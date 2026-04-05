#!/usr/bin/env python3
"""
Cross-Model Pragma Synthesis (CMPS) experiment.
Takes Qwen's PIPELINE/UNROLL + Gemma4's PARTITION → merge into one.
Compares against each model alone and Best-of-2.

Full IO logging for every step.
"""
import json, time, re, math, urllib.request, sys
sys.stdout.reconfigure(line_buffering=True)

CALL_LOG = []

def ollama_call(prompt, model, max_tokens=2048):
    t0 = time.time()
    data = json.dumps({
        'model': model, 'prompt': prompt, 'stream': False,
        'options': {'num_predict': max_tokens, 'temperature': 0.3},
    }).encode()
    req = urllib.request.Request('http://localhost:11434/api/generate',
                                data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            response = json.loads(resp.read()).get('response', '')
    except Exception as e:
        response = f'ERROR: {e}'
    elapsed = time.time() - t0
    CALL_LOG.append({
        'model': model, 'elapsed_sec': round(elapsed, 1),
        'prompt': prompt, 'response': response,
    })
    return response

def extract_code(text):
    for lang in ['c', 'cpp', '']:
        m = re.search(rf'```{lang}\s*\n(.*?)```', text, re.DOTALL)
        if m: return m.group(1).strip()
    return None

def extract_pragmas(code):
    return [l.strip() for l in code.split('\n') if '#pragma HLS' in l]

# ===== PRAGMA MERGER (rule-based) =====
def classify_pragma(p):
    """Classify pragma into LOOP (pipeline/unroll) or MEMORY (partition)."""
    p_upper = p.upper()
    if 'PIPELINE' in p_upper: return 'LOOP'
    if 'UNROLL' in p_upper: return 'LOOP'
    if 'PARTITION' in p_upper or 'RESHAPE' in p_upper: return 'MEMORY'
    if 'INTERFACE' in p_upper: return 'INTERFACE'
    return 'OTHER'

def merge_pragmas_cmps(qwen_pragmas, gemma_pragmas):
    """
    Cross-Model Pragma Synthesis:
    - LOOP pragmas (PIPELINE, UNROLL) from Qwen
    - MEMORY pragmas (PARTITION) from Gemma4
    - INTERFACE/OTHER: take from whichever has it
    """
    merged = []
    sources = {}  # track which model each pragma came from

    # Gemma4's MEMORY pragmas
    for p in gemma_pragmas:
        if classify_pragma(p) == 'MEMORY':
            merged.append(p)
            sources[p] = 'gemma4'

    # Qwen's LOOP pragmas
    for p in qwen_pragmas:
        cat = classify_pragma(p)
        if cat == 'LOOP':
            merged.append(p)
            sources[p] = 'qwen'
        elif cat in ('INTERFACE', 'OTHER'):
            if not any(classify_pragma(m) == cat for m in merged):
                merged.append(p)
                sources[p] = 'qwen'

    # If Gemma4 had LOOP pragmas that Qwen missed, add them
    for p in gemma_pragmas:
        cat = classify_pragma(p)
        if cat == 'LOOP' and not any(classify_pragma(m) == 'LOOP' and m != p for m in merged):
            # Only add if Qwen has NO loop pragmas at all
            if not any(classify_pragma(m) == 'LOOP' for m in merged if sources.get(m) == 'qwen'):
                merged.append(p)
                sources[p] = 'gemma4_fallback'

    return merged, sources

# ===== SCORING =====
def parse_param(p):
    r = {}
    if 'PIPELINE' in p and 'OFF' not in p:
        r['type'] = 'PIPELINE'; m = re.search(r'II\s*=\s*(\d+)', p); r['II'] = int(m.group(1)) if m else 1
    elif 'UNROLL' in p:
        r['type'] = 'UNROLL'; m = re.search(r'factor\s*=\s*(\d+)', p); r['factor'] = int(m.group(1)) if m else 16
    elif 'PARTITION' in p:
        r['type'] = 'PARTITION'; m = re.search(r'factor\s*=\s*(\d+)', p)
        r['factor'] = int(m.group(1)) if m else (32 if 'complete' in p else 1)
    return r

def pfs(llm_p, par_p):
    lp = [parse_param(x) for x in llm_p]; pp = [parse_param(x) for x in par_p]
    if not pp: return 1.0
    scores = []
    for p in pp:
        t = p.get('type','')
        m = next((x for x in lp if x.get('type')==t), None)
        if not m: scores.append(0.0); continue
        ps = []
        for k in ['II','factor']:
            if k in p and p[k] and k in m and m[k]:
                if p[k]==0 or m[k]==0: ps.append(1.0 if p[k]==m[k] else 0.0)
                else: ps.append(max(0, 1-abs(math.log2(m[k]/p[k]))/5))
        scores.append(sum(ps)/len(ps) if ps else 1.0)
    return sum(scores)/len(scores)

def tm(llm_p, par_p):
    lt,pt = set(),set()
    for p in llm_p:
        if 'PIPELINE' in p and 'OFF' not in p: lt.add('P')
        if 'UNROLL' in p and 'factor=1' not in p: lt.add('U')
        if 'PARTITION' in p: lt.add('A')
    for p in par_p:
        if 'PIPELINE' in p and 'OFF' not in p: pt.add('P')
        if 'UNROLL' in p and 'factor=1' not in p: pt.add('U')
        if 'PARTITION' in p: pt.add('A')
    a = pt|{'P','U','A'}
    return sum(1 for t in a if (t in lt)==(t in pt))/len(a)

# ===== KERNELS =====
KERNELS = {
    'fir_filter': {
        'code': """#define N 128\n#define TAPS 16\nvoid fir_filter(int input[N], int output[N], int coeffs[TAPS]) {\n    #pragma HLS PIPELINE OFF\n    #pragma HLS ARRAY_PARTITION variable=coeffs type=cyclic dim=1 factor=1\n    int i, j;\n    for (i = 0; i < N; i++) {\n        #pragma HLS PIPELINE OFF\n        int acc = 0;\n        for (j = 0; j < TAPS; j++) {\n            #pragma HLS UNROLL factor=1\n            int idx = i - j;\n            if (idx >= 0) acc += input[idx] * coeffs[j];\n        }\n        output[i] = acc;\n    }\n}""",
        'pareto': ['#pragma HLS PIPELINE II=1', '#pragma HLS ARRAY_PARTITION variable=coeffs type=complete dim=1', '#pragma HLS PIPELINE II=1', '#pragma HLS UNROLL factor=16'],
    },
    'gemm': {
        'code': """#define N 32\nvoid gemm(int A[N][N], int B[N][N], int C[N][N]) {\n    #pragma HLS PIPELINE OFF\n    int i, j, k;\n    for (i = 0; i < N; i++) {\n        for (j = 0; j < N; j++) {\n            #pragma HLS PIPELINE OFF\n            int sum = 0;\n            for (k = 0; k < N; k++) {\n                #pragma HLS UNROLL factor=1\n                sum += A[i][k] * B[k][j];\n            }\n            C[i][j] = sum;\n        }\n    }\n}""",
        'pareto': ['#pragma HLS ARRAY_PARTITION variable=B type=cyclic dim=2 factor=8', '#pragma HLS PIPELINE II=1', '#pragma HLS UNROLL factor=8'],
    },
    'dct': {
        'code': """#define N 8\nvoid dct(int input[N][N], int output[N][N], int cos_table[N][N]) {\n    int i, j, k;\n    for (i = 0; i < N; i++) {\n        for (j = 0; j < N; j++) {\n            #pragma HLS PIPELINE OFF\n            int sum = 0;\n            for (k = 0; k < N; k++)\n                #pragma HLS UNROLL factor=1\n                sum += input[i][k] * cos_table[k][j];\n            output[i][j] = sum >> 8;\n        }\n    }\n}""",
        'pareto': ['#pragma HLS ARRAY_PARTITION variable=cos_table type=complete dim=1', '#pragma HLS PIPELINE II=1', '#pragma HLS UNROLL'],
    },
    'stencil2d': {
        'code': """#define N 32\nvoid stencil2d(int orig[N][N], int sol[N][N], int filter[3][3]) {\n    int i, j, k, l;\n    for (i = 1; i < N-1; i++) {\n        for (j = 1; j < N-1; j++) {\n            #pragma HLS PIPELINE OFF\n            int sum = 0;\n            for (k = -1; k <= 1; k++)\n                for (l = -1; l <= 1; l++)\n                    #pragma HLS UNROLL factor=1\n                    sum += orig[i+k][j+l] * filter[k+1][l+1];\n            sol[i][j] = sum;\n        }\n    }\n}""",
        'pareto': ['#pragma HLS ARRAY_PARTITION variable=filter type=complete', '#pragma HLS PIPELINE II=1', '#pragma HLS UNROLL'],
    },
    'black_scholes': {
        'code': """#define N 64\nvoid black_scholes(int put[N], int call[N], int T[N], int S[N], int K[N], int r[N]) {\n    #pragma HLS PIPELINE OFF\n    int i;\n    for (i = 0; i < N; i++) {\n        #pragma HLS PIPELINE OFF\n        #pragma HLS UNROLL factor=1\n        int d1 = (S[i] - K[i] + r[i] * T[i]) >> 4;\n        int d2 = d1 - (T[i] >> 2);\n        call[i] = S[i] * d1 - K[i] * d2;\n        put[i] = K[i] * (-d2) - S[i] * (-d1);\n    }\n}""",
        'pareto': ['#pragma HLS ARRAY_PARTITION variable=S type=cyclic dim=1 factor=16', '#pragma HLS PIPELINE II=1', '#pragma HLS UNROLL factor=8'],
    },
}

PROMPT = """Optimize this HLS C code for minimum latency on Xilinx FPGA.
Use #pragma HLS: PIPELINE II=1, UNROLL (factor 4-16), ARRAY_PARTITION.
Resource budget: 80% LUT/DSP. Algorithm: {algo}

```c
{code}
```

Output optimized code in a ```c``` block."""

def main():
    ts = int(time.time())
    all_results = {}

    for algo, d in KERNELS.items():
        print(f"\n{'='*60}")
        print(f"  {algo}")
        print(f"{'='*60}")

        pp = d['pareto']
        print(f"  Pareto: {pp[:3]}")

        # 1. Qwen alone
        resp_q = ollama_call(PROMPT.format(algo=algo, code=d['code']), 'qwen2.5-coder:7b')
        code_q = extract_code(resp_q)
        qwen_pragmas = extract_pragmas(code_q) if code_q else []
        pfs_q = pfs(qwen_pragmas, pp); tm_q = tm(qwen_pragmas, pp)
        print(f"  Qwen:   TM={tm_q:.0%} PFS={pfs_q:.3f} | {qwen_pragmas[:3]}")

        # 2. Gemma4 alone
        resp_g = ollama_call(PROMPT.format(algo=algo, code=d['code']), 'gemma4:latest')
        code_g = extract_code(resp_g)
        gemma_pragmas = extract_pragmas(code_g) if code_g else []
        pfs_g = pfs(gemma_pragmas, pp); tm_g = tm(gemma_pragmas, pp)
        print(f"  Gemma4: TM={tm_g:.0%} PFS={pfs_g:.3f} | {gemma_pragmas[:3]}")

        # 3. CMPS Merge
        merged, sources = merge_pragmas_cmps(qwen_pragmas, gemma_pragmas)
        pfs_m = pfs(merged, pp); tm_m = tm(merged, pp)
        print(f"  CMPS:   TM={tm_m:.0%} PFS={pfs_m:.3f} | {merged[:4]}")
        print(f"    Sources: {sources}")

        # 4. Best-of-2 (pick whichever has higher PFS)
        if pfs_q >= pfs_g:
            best2_pragmas = qwen_pragmas; best2_winner = 'qwen'
        else:
            best2_pragmas = gemma_pragmas; best2_winner = 'gemma4'
        pfs_b = pfs(best2_pragmas, pp); tm_b = tm(best2_pragmas, pp)
        print(f"  Best2:  TM={tm_b:.0%} PFS={pfs_b:.3f} (winner={best2_winner})")

        all_results[algo] = {
            'pareto': pp,
            'qwen': {'pragmas': qwen_pragmas, 'pfs': round(pfs_q, 3), 'tm': round(tm_q, 3),
                     'raw_response': resp_q[:2000]},
            'gemma4': {'pragmas': gemma_pragmas, 'pfs': round(pfs_g, 3), 'tm': round(tm_g, 3),
                       'raw_response': resp_g[:2000]},
            'cmps': {'pragmas': merged, 'sources': {str(k): v for k, v in sources.items()},
                     'pfs': round(pfs_m, 3), 'tm': round(tm_m, 3)},
            'best_of_2': {'pragmas': best2_pragmas, 'pfs': round(pfs_b, 3), 'winner': best2_winner},
        }

    # Summary
    print(f"\n{'='*60}")
    print(f"  CMPS EXPERIMENT SUMMARY")
    print(f"{'='*60}")
    print(f"{'Kernel':<20} {'Qwen':>8} {'Gemma4':>8} {'CMPS':>8} {'Best2':>8}")
    for algo, r in all_results.items():
        print(f"{algo:<20} {r['qwen']['pfs']:>8.3f} {r['gemma4']['pfs']:>8.3f} {r['cmps']['pfs']:>8.3f} {r['best_of_2']['pfs']:>8.3f}")

    # Averages
    n = len(all_results)
    avg_q = sum(r['qwen']['pfs'] for r in all_results.values()) / n
    avg_g = sum(r['gemma4']['pfs'] for r in all_results.values()) / n
    avg_m = sum(r['cmps']['pfs'] for r in all_results.values()) / n
    avg_b = sum(r['best_of_2']['pfs'] for r in all_results.values()) / n
    print(f"{'AVERAGE':<20} {avg_q:>8.3f} {avg_g:>8.3f} {avg_m:>8.3f} {avg_b:>8.3f}")

    # Save
    out = {'timestamp': ts, 'results': all_results, 'call_log': CALL_LOG,
           'averages': {'qwen': round(avg_q,3), 'gemma4': round(avg_g,3),
                        'cmps': round(avg_m,3), 'best_of_2': round(avg_b,3)}}
    outf = f'/root/cmps_results_{ts}.json'
    with open(outf, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: {outf} ({len(CALL_LOG)} calls logged)")

if __name__ == '__main__':
    main()
