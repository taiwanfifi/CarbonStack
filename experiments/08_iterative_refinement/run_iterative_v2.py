#!/usr/bin/env python3
"""
Iterative Refinement v2: LLM → Vitis → structured feedback → LLM → repeat.
Fixed feedback format to prevent DSP explosion.

Runs on Vast.ai GPU, SSHs to AWS for Vitis synthesis.
Or runs locally with Bambu Docker.

Key improvement: resource-budget-aware feedback with step-size limits.
"""
import json, time, re, urllib.request, subprocess, sys, os
sys.stdout.reconfigure(line_buffering=True)

# ===== CONFIG =====
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
MODEL = os.environ.get("MODEL", "gemma4:latest")
VITIS_SSH = os.environ.get("VITIS_SSH", "")  # e.g. "ubuntu@54.209.27.215"
VITIS_KEY = os.environ.get("VITIS_KEY", "")  # e.g. "~/Downloads/vitis-key.pem"
MAX_ROUNDS = int(os.environ.get("MAX_ROUNDS", "5"))

# Resource budgets (reasonable for medium kernels)
BUDGET = {"dsp": 50, "lut": 10000, "ff": 20000, "bram": 20}

def llm_call(prompt, max_tokens=2048):
    data = json.dumps({"model": MODEL, "prompt": prompt, "stream": False,
                       "options": {"num_predict": max_tokens, "temperature": 0.3}}).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/generate",
                                data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read()).get("response", "")

def extract_code(text):
    for lang in ["c", "cpp", ""]:
        m = re.search(rf"```{lang}\s*\n(.*?)```", text, re.DOTALL)
        if m: return m.group(1).strip()
    return None

def extract_pragmas(code):
    return [l.strip() for l in code.split("\n") if "#pragma HLS" in l]

def merge_pragmas(original, llm_output):
    if not llm_output: return original
    orig_lines = original.split("\n")
    llm_pragmas = [l.strip() for l in llm_output.split("\n") if "#pragma HLS" in l]
    pragma_pos = [i for i, l in enumerate(orig_lines) if "#pragma HLS" in l]
    merged = orig_lines.copy()
    for idx, pos in enumerate(pragma_pos):
        if idx < len(llm_pragmas):
            indent = len(orig_lines[pos]) - len(orig_lines[pos].lstrip())
            merged[pos] = " " * indent + llm_pragmas[idx]
    return "\n".join(merged)

def format_feedback(metrics, prev_metrics=None):
    """Structured feedback that prevents over-aggressive optimization."""
    if not metrics.get("success"):
        return ("SYNTHESIS FAILED. Your pragmas caused a compilation error.\n"
                "Please simplify: use fewer PARTITION directives and smaller UNROLL factors.")

    lines = ["=== Vitis HLS Synthesis Report ==="]
    lines.append(f"Latency: {metrics['latency']} clock cycles")

    for res in ["dsp", "lut", "ff"]:
        val = metrics.get(res, 0)
        budget = BUDGET.get(res, 999)
        pct = val / budget * 100
        status = "OK" if pct < 60 else ("CAUTION" if pct < 80 else "OVER BUDGET")
        lines.append(f"  {res.upper()}: {val}/{budget} ({pct:.0f}%) [{status}]")

    if metrics.get("achieved_ii"):
        ii = metrics["achieved_ii"]
        lines.append(f"Pipeline II: {ii}" + (" (optimal)" if ii == 1 else f" (target: 1, gap: {ii-1})"))

    # Comparison with previous round
    if prev_metrics and prev_metrics.get("latency"):
        prev_lat = prev_metrics["latency"]
        curr_lat = metrics["latency"]
        if curr_lat < prev_lat:
            lines.append(f"\nIMPROVED: {prev_lat}→{curr_lat} cycles ({(prev_lat-curr_lat)/prev_lat*100:.1f}% reduction)")
        elif curr_lat > prev_lat:
            lines.append(f"\nREGRESSED: {prev_lat}→{curr_lat} cycles. REVERT your last change.")
            lines.append("Try a LESS aggressive approach.")
        else:
            lines.append(f"\nNO CHANGE: still {curr_lat} cycles. Try a DIFFERENT optimization.")

    # Action constraints
    lines.append("\n=== Rules ===")
    lines.append("1. Change at MOST 2 pragma parameters per round")
    lines.append("2. Do NOT use ARRAY_PARTITION complete on arrays larger than 32 elements")
    lines.append("3. UNROLL factor must be a power of 2 and ≤ loop trip count")
    lines.append("4. Keep all non-pragma code lines EXACTLY unchanged")

    return "\n".join(lines)

INITIAL_PROMPT = """Optimize this HLS C code for minimum latency on Xilinx FPGA.
Use #pragma HLS: PIPELINE II=1, UNROLL (factor 4-16), ARRAY_PARTITION (cyclic or complete for small arrays).
Resource budget: DSP≤{dsp}, LUT≤{lut}.
Algorithm: {algo}

```c
{code}
```

Output the optimized code in a ```c``` block."""

REFINE_PROMPT = """You are iteratively optimizing HLS C code. Here is the synthesis feedback from Vitis HLS:

{feedback}

Current code:
```c
{code}
```

Based on the feedback, improve the pragmas to reduce latency further.
Follow the rules in the feedback. Output improved code in a ```c``` block."""

# Test kernels
KERNELS = {
    "fir": {
        "code": """#define N 128
#define TAPS 16
void fir_filter(int input[N], int output[N], int coeffs[TAPS]) {
    #pragma HLS PIPELINE OFF
    #pragma HLS ARRAY_PARTITION variable=coeffs type=cyclic dim=1 factor=1
    int i, j;
    for (i = 0; i < N; i++) {
        #pragma HLS PIPELINE OFF
        int acc = 0;
        for (j = 0; j < TAPS; j++) {
            #pragma HLS UNROLL factor=1
            int idx = i - j;
            if (idx >= 0) acc += input[idx] * coeffs[j];
        }
        output[i] = acc;
    }
}""",
        "top": "fir_filter",
    },
    "gemm": {
        "code": """#define N 32
void gemm(int A[N][N], int B[N][N], int C[N][N]) {
    #pragma HLS PIPELINE OFF
    int i, j, k;
    for (i = 0; i < N; i++) {
        for (j = 0; j < N; j++) {
            #pragma HLS PIPELINE OFF
            int sum = 0;
            for (k = 0; k < N; k++) {
                #pragma HLS UNROLL factor=1
                sum += A[i][k] * B[k][j];
            }
            C[i][j] = sum;
        }
    }
}""",
        "top": "gemm",
    },
    "dct": {
        "code": """#define N 8
void dct(int input[N][N], int output[N][N], int cos_table[N][N]) {
    int i, j, k;
    for (i = 0; i < N; i++) {
        for (j = 0; j < N; j++) {
            #pragma HLS PIPELINE OFF
            int sum = 0;
            for (k = 0; k < N; k++)
                #pragma HLS UNROLL factor=1
                sum += input[i][k] * cos_table[k][j];
            output[i][j] = sum >> 8;
        }
    }
}""",
        "top": "dct",
    },
}

def main():
    ts = int(time.time())
    all_results = {}

    for kname, kdata in KERNELS.items():
        print(f"\n{'='*60}")
        print(f"  Iterative Refinement: {kname} (max {MAX_ROUNDS} rounds)")
        print(f"{'='*60}")

        original_code = kdata["code"]
        top_fn = kdata["top"]
        history = []
        current_code = original_code
        best_latency = float("inf")
        best_code = original_code

        for r in range(MAX_ROUNDS):
            print(f"\n  Round {r}:", end=" ", flush=True)

            if r == 0:
                # Initial LLM suggestion
                prompt = INITIAL_PROMPT.format(
                    dsp=BUDGET["dsp"], lut=BUDGET["lut"],
                    algo=kname, code=original_code
                )
            else:
                # Refinement with feedback
                feedback = format_feedback(
                    history[-1]["metrics"],
                    history[-2]["metrics"] if len(history) >= 2 else None
                )
                prompt = REFINE_PROMPT.format(feedback=feedback, code=current_code)

            # LLM call
            resp = llm_call(prompt)
            llm_code = extract_code(resp)

            if not llm_code:
                print("LLM FAILED (no code block)")
                history.append({"round": r, "success": False, "error": "no_code"})
                continue

            # Post-process merge
            merged = merge_pragmas(original_code, llm_code)
            pragmas = extract_pragmas(merged)

            # Simulate synthesis (for now, just record pragmas)
            # In real run: call Vitis on AWS
            metrics = {
                "success": True,
                "pragmas": pragmas,
                "pragma_count": len(pragmas),
            }

            print(f"{len(pragmas)} pragmas: {pragmas[:3]}")

            history.append({
                "round": r,
                "metrics": metrics,
                "pragmas": pragmas,
                "prompt_len": len(prompt),
                "response_len": len(resp),
            })

            current_code = merged

        all_results[kname] = history

    # Save
    outf = f"iterative_v2_{ts}.json"
    with open(outf, "w") as f:
        json.dump({"config": {"model": MODEL, "max_rounds": MAX_ROUNDS, "budget": BUDGET},
                   "results": all_results}, f, indent=2)
    print(f"\nSaved: {outf}")

if __name__ == "__main__":
    main()
