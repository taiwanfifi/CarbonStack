import json, time, re, math, urllib.request, sys, random
sys.stdout.reconfigure(line_buffering=True)

def call(prompt, model="gemma4:latest", max_tokens=2048, temp=0.3):
    data = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"num_predict": max_tokens, "temperature": temp}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate",
                                data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read()).get("response", "")

def ext(text):
    for l in ["c", "cpp", ""]:
        m = re.search(r"```" + l + r"\s*\n(.*?)```", text, re.DOTALL)
        if m: return m.group(1).strip()
    return None

def extract_pragmas(code):
    return [l.strip() for l in code.split("\n") if "#pragma HLS" in l]

def parse_param(p):
    r = {}
    if "PIPELINE" in p and "OFF" not in p:
        r["type"] = "PIPELINE"; m = re.search(r"II\s*=\s*(\d+)", p); r["II"] = int(m.group(1)) if m else 1
    elif "UNROLL" in p:
        r["type"] = "UNROLL"; m = re.search(r"factor\s*=\s*(\d+)", p); r["factor"] = int(m.group(1)) if m else 16
    elif "PARTITION" in p:
        r["type"] = "PARTITION"; m = re.search(r"factor\s*=\s*(\d+)", p)
        r["factor"] = int(m.group(1)) if m else (32 if "complete" in p else 1)
    return r

def pfs(llm_p, par_p):
    lp = [parse_param(x) for x in llm_p]; pp = [parse_param(x) for x in par_p]
    if not pp: return 1.0
    scores = []
    for p in pp:
        t = p.get("type", "")
        m = next((x for x in lp if x.get("type") == t), None)
        if not m: scores.append(0.0); continue
        ps = []
        for k in ["II", "factor"]:
            if k in p and p[k] and k in m and m[k]:
                if p[k] == 0 or m[k] == 0: ps.append(1.0 if p[k] == m[k] else 0.0)
                else: ps.append(max(0, 1 - abs(math.log2(m[k] / p[k])) / 5))
        scores.append(sum(ps) / len(ps) if ps else 1.0)
    return sum(scores) / len(scores)

def tm(llm_p, par_p):
    lt, pt = set(), set()
    for p in llm_p:
        if "PIPELINE" in p and "OFF" not in p: lt.add("P")
        if "UNROLL" in p and "factor=1" not in p: lt.add("U")
        if "PARTITION" in p: lt.add("A")
    for p in par_p:
        if "PIPELINE" in p and "OFF" not in p: pt.add("P")
        if "UNROLL" in p and "factor=1" not in p: pt.add("U")
        if "PARTITION" in p: pt.add("A")
    a = pt | {"P", "U", "A"}
    return sum(1 for t in a if (t in lt) == (t in pt)) / len(a)

KERNELS = {
    "fir_filter": {
        "code": "#define N 128\n#define TAPS 16\nvoid fir_filter(int input[N], int output[N], int coeffs[TAPS]) {\n    #pragma HLS PIPELINE OFF\n    #pragma HLS ARRAY_PARTITION variable=coeffs type=cyclic dim=1 factor=1\n    int i, j;\n    for (i = 0; i < N; i++) {\n        #pragma HLS PIPELINE OFF\n        int acc = 0;\n        for (j = 0; j < TAPS; j++) {\n            #pragma HLS UNROLL factor=1\n            int idx = i - j;\n            if (idx >= 0) acc += input[idx] * coeffs[j];\n        }\n        output[i] = acc;\n    }\n}",
        "pareto": ["#pragma HLS PIPELINE II=1", "#pragma HLS ARRAY_PARTITION variable=coeffs type=complete dim=1", "#pragma HLS PIPELINE II=1", "#pragma HLS UNROLL factor=16"],
    },
    "gemm": {
        "code": "#define N 32\nvoid gemm(int A[N][N], int B[N][N], int C[N][N]) {\n    #pragma HLS PIPELINE OFF\n    int i, j, k;\n    for (i = 0; i < N; i++) {\n        for (j = 0; j < N; j++) {\n            #pragma HLS PIPELINE OFF\n            int sum = 0;\n            for (k = 0; k < N; k++) {\n                #pragma HLS UNROLL factor=1\n                sum += A[i][k] * B[k][j];\n            }\n            C[i][j] = sum;\n        }\n    }\n}",
        "pareto": ["#pragma HLS ARRAY_PARTITION variable=B type=cyclic dim=2 factor=8", "#pragma HLS PIPELINE II=1", "#pragma HLS UNROLL factor=8"],
    },
    "dct": {
        "code": "#define N 8\nvoid dct(int input[N][N], int output[N][N], int cos_table[N][N]) {\n    int i, j, k;\n    for (i = 0; i < N; i++) {\n        for (j = 0; j < N; j++) {\n            #pragma HLS PIPELINE OFF\n            int sum = 0;\n            for (k = 0; k < N; k++)\n                #pragma HLS UNROLL factor=1\n                sum += input[i][k] * cos_table[k][j];\n            output[i][j] = sum >> 8;\n        }\n    }\n}",
        "pareto": ["#pragma HLS ARRAY_PARTITION variable=cos_table type=complete dim=1", "#pragma HLS PIPELINE II=1", "#pragma HLS UNROLL"],
    },
    "stencil2d": {
        "code": "#define N 32\nvoid stencil2d(int orig[N][N], int sol[N][N], int filter[3][3]) {\n    int i, j, k, l;\n    for (i = 1; i < N-1; i++) {\n        for (j = 1; j < N-1; j++) {\n            #pragma HLS PIPELINE OFF\n            int sum = 0;\n            for (k = -1; k <= 1; k++)\n                for (l = -1; l <= 1; l++)\n                    #pragma HLS UNROLL factor=1\n                    sum += orig[i+k][j+l] * filter[k+1][l+1];\n            sol[i][j] = sum;\n        }\n    }\n}",
        "pareto": ["#pragma HLS ARRAY_PARTITION variable=filter type=complete", "#pragma HLS PIPELINE II=1", "#pragma HLS UNROLL"],
    },
    "black_scholes": {
        "code": "#define N 64\nvoid black_scholes(int put[N], int call[N], int T[N], int S[N], int K[N], int r[N]) {\n    #pragma HLS PIPELINE OFF\n    int i;\n    for (i = 0; i < N; i++) {\n        #pragma HLS PIPELINE OFF\n        #pragma HLS UNROLL factor=1\n        int d1 = (S[i] - K[i] + r[i] * T[i]) >> 4;\n        int d2 = d1 - (T[i] >> 2);\n        call[i] = S[i] * d1 - K[i] * d2;\n        put[i] = K[i] * (-d2) - S[i] * (-d1);\n    }\n}",
        "pareto": ["#pragma HLS ARRAY_PARTITION variable=S type=cyclic dim=1 factor=16", "#pragma HLS PIPELINE II=1", "#pragma HLS UNROLL factor=8"],
    },
}

PROMPT_FULL = """Optimize this HLS C code for minimum latency on Xilinx FPGA.
Use #pragma HLS: PIPELINE II=1, UNROLL (factor 4-16), ARRAY_PARTITION.
Resource budget: 80% LUT/DSP. Algorithm: {algo}

```c
{code}
```

Output optimized code in a ```c``` block."""

PROMPT_NO_PARTITION = """Optimize this HLS C code for minimum latency on Xilinx FPGA.
Use ONLY #pragma HLS PIPELINE and UNROLL. Do NOT use ARRAY_PARTITION.
Algorithm: {algo}

```c
{code}
```

Output optimized code in a ```c``` block."""

PROMPT_NO_PIPELINE = """Optimize this HLS C code for minimum latency on Xilinx FPGA.
Use ONLY #pragma HLS ARRAY_PARTITION and UNROLL. Do NOT use PIPELINE.
Algorithm: {algo}

```c
{code}
```

Output optimized code in a ```c``` block."""

ts = int(time.time())
all_results = {}

# ===== EXPERIMENT 1: Multi-seed statistics (5 seeds) =====
print("=" * 60)
print("  EXPERIMENT 1: Multi-seed Statistics (Gemma4, 5 seeds)")
print("=" * 60)

seed_results = {}
for seed in range(5):
    print("\n--- Seed {} ---".format(seed))
    temp = 0.3 + seed * 0.1  # vary temperature: 0.3, 0.4, 0.5, 0.6, 0.7
    run = []
    for algo, d in KERNELS.items():
        resp = call(PROMPT_FULL.format(algo=algo, code=d["code"]), temp=temp)
        code = ext(resp)
        if code:
            lp = extract_pragmas(code)
            p = pfs(lp, d["pareto"])
            t = tm(lp, d["pareto"])
            print("  {} TM={:.0%} PFS={:.3f}".format(algo, t, p))
            run.append({"algo": algo, "tm": round(t, 3), "pfs": round(p, 3), "temp": temp})
        else:
            print("  {} FAILED".format(algo))
            run.append({"algo": algo, "tm": 0, "pfs": 0, "temp": temp, "failed": True})
    seed_results["seed_{}".format(seed)] = run

all_results["multi_seed"] = seed_results

# Compute stats
print("\n--- Multi-seed Summary ---")
for algo in KERNELS:
    pfss = [r["pfs"] for seed_data in seed_results.values()
            for r in seed_data if r["algo"] == algo and not r.get("failed")]
    if pfss:
        mean_pfs = sum(pfss) / len(pfss)
        std_pfs = (sum((x - mean_pfs) ** 2 for x in pfss) / len(pfss)) ** 0.5
        print("  {}: PFS mean={:.3f} std={:.3f} min={:.3f} max={:.3f} (n={})".format(
            algo, mean_pfs, std_pfs, min(pfss), max(pfss), len(pfss)))

# ===== EXPERIMENT 2: Ablation Study =====
print("\n" + "=" * 60)
print("  EXPERIMENT 2: Ablation Study (Gemma4)")
print("=" * 60)

ablation_configs = [
    ("full", PROMPT_FULL),
    ("no_partition", PROMPT_NO_PARTITION),
    ("no_pipeline", PROMPT_NO_PIPELINE),
]

ablation_results = {}
for config_name, prompt_template in ablation_configs:
    print("\n--- Config: {} ---".format(config_name))
    run = []
    for algo, d in KERNELS.items():
        resp = call(prompt_template.format(algo=algo, code=d["code"]))
        code = ext(resp)
        if code:
            lp = extract_pragmas(code)
            p = pfs(lp, d["pareto"])
            t = tm(lp, d["pareto"])
            print("  {} TM={:.0%} PFS={:.3f}".format(algo, t, p))
            run.append({"algo": algo, "tm": round(t, 3), "pfs": round(p, 3),
                        "pragmas": lp[:5]})
        else:
            print("  {} FAILED".format(algo))
            run.append({"algo": algo, "failed": True})
    ablation_results[config_name] = run

all_results["ablation"] = ablation_results

# Ablation summary
print("\n--- Ablation Summary ---")
print("{:<20} {:>8} {:>8}".format("Config", "Avg TM", "Avg PFS"))
for config_name, run in ablation_results.items():
    ok = [r for r in run if not r.get("failed")]
    if ok:
        avg_tm = sum(r["tm"] for r in ok) / len(ok)
        avg_pfs = sum(r["pfs"] for r in ok) / len(ok)
        print("{:<20} {:>7.1%} {:>8.3f}".format(config_name, avg_tm, avg_pfs))

# ===== EXPERIMENT 3: Model comparison (same prompt, different models) =====
print("\n" + "=" * 60)
print("  EXPERIMENT 3: Model Comparison (same prompt)")
print("=" * 60)

models = ["gemma4:latest", "qwen2.5-coder:7b"]
model_results = {}
for model in models:
    print("\n--- Model: {} ---".format(model))
    run = []
    for algo, d in KERNELS.items():
        resp = call(PROMPT_FULL.format(algo=algo, code=d["code"]), model=model)
        code = ext(resp)
        if code:
            lp = extract_pragmas(code)
            p = pfs(lp, d["pareto"])
            t = tm(lp, d["pareto"])
            print("  {} TM={:.0%} PFS={:.3f}".format(algo, t, p))
            run.append({"algo": algo, "tm": round(t, 3), "pfs": round(p, 3)})
        else:
            print("  {} FAILED".format(algo))
            run.append({"algo": algo, "failed": True})
    model_results[model] = run

all_results["model_comparison"] = model_results

# Save
outf = "/root/stats_ablation_{}.json".format(ts)
with open(outf, "w") as f:
    json.dump(all_results, f, indent=2)
print("\nSaved: {}".format(outf))
