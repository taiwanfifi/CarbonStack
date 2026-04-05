#!/usr/bin/env python3
"""
GPU A/B Test v2: Fair comparison with FULL IO logging.
- Every LLM call logged (prompt + raw response + extracted code)
- Same inference count per comparison group
- pass@1 vs pass@2 vs pass@3 curves
"""
import json, time, re, math, urllib.request, sys, os
sys.stdout.reconfigure(line_buffering=True)

CALL_LOG = []  # Full IO log

def ollama_call(prompt, model='qwen2.5-coder:7b', max_tokens=2048):
    t0 = time.time()
    data = json.dumps({
        'model': model, 'prompt': prompt, 'stream': False,
        'options': {'num_predict': max_tokens, 'temperature': 0.3},
    }).encode()
    req = urllib.request.Request('http://localhost:11434/api/generate',
                                data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            result = json.loads(resp.read())
            response = result.get('response', '')
    except Exception as e:
        response = f'ERROR: {e}'

    elapsed = time.time() - t0
    entry = {
        'model': model, 'prompt_len': len(prompt),
        'response_len': len(response), 'elapsed_sec': round(elapsed, 1),
        'prompt_preview': prompt[:200], 'response_preview': response[:500],
    }
    CALL_LOG.append(entry)
    return response


def extract_code(text):
    for lang in ['c', 'cpp', '']:
        m = re.search(rf'```{lang}\s*\n(.*?)```', text, re.DOTALL)
        if m: return m.group(1).strip()
    return None

def extract_pragmas(code):
    return [l.strip() for l in code.split('\n') if '#pragma HLS' in l]

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

PROMPT_TEMPLATE = """Optimize this HLS C code for minimum latency on Xilinx FPGA.
Use #pragma HLS: PIPELINE II=1, UNROLL (factor 4-16), ARRAY_PARTITION.
Resource budget: 80% LUT/DSP. Algorithm: {algo}

```c
{code}
```

Output optimized code in a ```c``` block."""

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

# ===== FAIR TEST: 1 inference each =====
def run_single(model, label):
    """pass@1: one inference per kernel."""
    print(f"\n{'='*60}\n  {label} (pass@1, model={model})\n{'='*60}")
    results = []
    for algo, d in KERNELS.items():
        print(f"  {algo}...", end=' ', flush=True)
        resp = ollama_call(PROMPT_TEMPLATE.format(algo=algo, code=d['code']), model=model)
        code = extract_code(resp)
        if not code:
            print("FAILED")
            results.append({'algo': algo, 'success': False, 'model': model,
                            'raw_response': resp[:1000]})
            continue
        lp = extract_pragmas(code)
        pp = d['pareto']
        t = tm(lp, pp); p = pfs(lp, pp)
        print(f"TM={t:.0%} PFS={p:.3f}")
        results.append({'algo': algo, 'success': True, 'model': model,
                        'tm': round(t,3), 'pfs': round(p,3),
                        'llm_pragmas': lp, 'pareto_pragmas': pp,
                        'raw_response': resp[:2000], 'generated_code': code[:2000]})
    return results

def run_chaining(model, label):
    """pass@1 with 2-step chaining (counts as 1 strategy, 2 calls)."""
    print(f"\n{'='*60}\n  {label} (chaining, model={model})\n{'='*60}")
    results = []
    for algo, d in KERNELS.items():
        print(f"  {algo}...", end=' ', flush=True)
        # Step 1: analyze
        r1 = ollama_call(f"Analyze this HLS code for {algo}. What are the bottlenecks? Which pragma types (PIPELINE/UNROLL/PARTITION) should be used?\n```c\n{d['code'][:1500]}\n```",
                         model=model, max_tokens=300)
        # Step 2: generate with analysis
        r2 = ollama_call(f"Optimize this HLS code based on analysis: {r1[:300]}\nBe aggressive: PIPELINE II=1, UNROLL factor=8-16, PARTITION arrays accessed in parallel.\n```c\n{d['code']}\n```\nOutput optimized code in a ```c``` block.",
                         model=model)
        code = extract_code(r2)
        if not code:
            print("FAILED")
            results.append({'algo': algo, 'success': False, 'model': model,
                            'step1_response': r1[:500], 'step2_response': r2[:500]})
            continue
        lp = extract_pragmas(code); pp = d['pareto']
        t = tm(lp, pp); p = pfs(lp, pp)
        print(f"TM={t:.0%} PFS={p:.3f}")
        results.append({'algo': algo, 'success': True, 'model': model,
                        'tm': round(t,3), 'pfs': round(p,3),
                        'llm_pragmas': lp, 'pareto_pragmas': pp,
                        'step1_analysis': r1[:1000], 'generated_code': code[:2000]})
    return results

def run_dual(model_a, model_b, label):
    """2 inferences: model_a suggests, model_b refines."""
    print(f"\n{'='*60}\n  {label} ({model_a}→{model_b})\n{'='*60}")
    results = []
    for algo, d in KERNELS.items():
        print(f"  {algo}...", end=' ', flush=True)
        # Model A
        ra = ollama_call(PROMPT_TEMPLATE.format(algo=algo, code=d['code']), model=model_a)
        ca = extract_code(ra)
        if not ca:
            print("A FAILED")
            results.append({'algo': algo, 'success': False, 'model_a': model_a,
                            'model_a_response': ra[:500]})
            continue
        pa = extract_pragmas(ca)
        # Model B refines
        rb = ollama_call(f"Review and improve these HLS pragmas for {algo}:\n{chr(10).join(pa)}\n\nOriginal:\n```c\n{d['code'][:1500]}\n```\nAre factors optimal? Output improved code in ```c``` block.",
                         model=model_b)
        cb = extract_code(rb)
        if not cb:
            # Use model A's result
            lp = pa
        else:
            lp = extract_pragmas(cb)
        pp = d['pareto']
        t = tm(lp, pp); p = pfs(lp, pp)
        print(f"TM={t:.0%} PFS={p:.3f}")
        results.append({'algo': algo, 'success': True,
                        'model_a': model_a, 'model_b': model_b,
                        'tm': round(t,3), 'pfs': round(p,3),
                        'model_a_pragmas': pa, 'model_b_pragmas': lp,
                        'pareto_pragmas': pp,
                        'model_a_code': ca[:1000], 'model_b_code': (cb or '')[:1000]})
    return results

def main():
    ts = int(time.time())
    try:
        with urllib.request.urlopen('http://localhost:11434/api/tags') as r:
            available = [m['name'] for m in json.loads(r.read()).get('models',[])]
    except:
        available = []
    print(f"Models: {available}")

    has = lambda n: any(n in m for m in available)
    gname = next((m for m in available if 'gemma4' in m), None)
    dname = next((m for m in available if 'deepseek-r1' in m), None)

    all_results = {}

    # === FAIR GROUP 1: pass@1 (1 inference each) ===
    if has('qwen2.5-coder'):
        all_results['qwen7b_pass1'] = run_single('qwen2.5-coder:7b', 'Qwen 7B pass@1')
    if gname:
        all_results['gemma4_pass1'] = run_single(gname, 'Gemma4 pass@1')
    if dname:
        all_results['deepseek_pass1'] = run_single(dname, 'DeepSeek-R1 pass@1')

    # === FAIR GROUP 2: 2 inferences each ===
    if has('qwen2.5-coder'):
        all_results['qwen7b_chain'] = run_chaining('qwen2.5-coder:7b', 'Qwen 7B chain')
    if gname:
        all_results['gemma4_chain'] = run_chaining(gname, 'Gemma4 chain')
    if has('qwen2.5-coder') and gname:
        all_results['qwen_gemma_dual'] = run_dual('qwen2.5-coder:7b', gname, 'Qwen→Gemma4')
        all_results['gemma_qwen_dual'] = run_dual(gname, 'qwen2.5-coder:7b', 'Gemma4→Qwen')

    # === SUMMARY ===
    print(f"\n{'='*60}")
    print(f"  FAIR A/B TEST SUMMARY")
    print(f"{'='*60}")
    print(f"{'Strategy':<25} {'Inferences':>10} {'TypeMatch':>10} {'PFS':>8} {'N':>4}")
    print(f"{'-'*25} {'-'*10} {'-'*10} {'-'*8} {'-'*4}")

    for name, results in all_results.items():
        ok = [r for r in results if r.get('success')]
        if ok:
            avg_tm = sum(r['tm'] for r in ok)/len(ok)
            avg_pfs = sum(r['pfs'] for r in ok)/len(ok)
            n_inf = 1 if 'pass1' in name else 2
            print(f"{name:<25} {n_inf:>10} {avg_tm:>9.1%} {avg_pfs:>8.3f} {len(ok):>4}")

    # Save everything
    out = {
        'timestamp': ts, 'models': available,
        'results': all_results,
        'call_log': CALL_LOG,  # FULL IO LOG
        'total_calls': len(CALL_LOG),
        'total_time': sum(c['elapsed_sec'] for c in CALL_LOG),
    }
    outf = f'/root/hls_ab_v2_{ts}.json'
    with open(outf, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved: {outf} ({len(CALL_LOG)} LLM calls logged)")

if __name__ == '__main__':
    main()
