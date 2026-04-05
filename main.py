#!/usr/bin/env python3
"""
CarbonCode CLI: HLS Pragma Optimization

Usage:
  python main.py optimize --input fir.c --top fir_filter
  python main.py optimize --input fir.c --top fir_filter --model gemma4
  python main.py evaluate --input fir.c --pareto pareto.c
  python main.py synthesize --input fir.c --top fir_filter --ssh user@host

One command: C code in → optimized C code out (with pragmas).
"""
import argparse
import json
import re
import sys
import os
import urllib.request

def ollama_call(prompt, model="gemma4:latest", url="http://localhost:11434", max_tokens=2048):
    """Call local ollama model."""
    data = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"num_predict": max_tokens, "temperature": 0.3}}).encode()
    req = urllib.request.Request(f"{url}/api/generate",
                                data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            return json.loads(resp.read()).get("response", "")
    except Exception as e:
        print(f"Error calling ollama: {e}", file=sys.stderr)
        print(f"Make sure ollama is running: ollama serve", file=sys.stderr)
        sys.exit(1)

def extract_code(text):
    for lang in ["c", "cpp", ""]:
        m = re.search(rf"```{lang}\s*\n(.*?)```", text, re.DOTALL)
        if m: return m.group(1).strip()
    return None

def extract_pragmas(code):
    return [l.strip() for l in code.split("\n") if "#pragma HLS" in l]

def merge_pragmas(original, llm_output):
    """Post-process merge: only replace pragma lines. 100% code safety."""
    if not llm_output:
        return original
    orig_lines = original.split("\n")
    llm_pragmas = [l.strip() for l in llm_output.split("\n") if "#pragma HLS" in l]
    pragma_pos = [i for i, l in enumerate(orig_lines) if "#pragma HLS" in l]
    merged = orig_lines.copy()
    for idx, pos in enumerate(pragma_pos):
        if idx < len(llm_pragmas):
            indent = len(orig_lines[pos]) - len(orig_lines[pos].lstrip())
            merged[pos] = " " * indent + llm_pragmas[idx]
    # If original has no pragmas but LLM suggests some, insert before for-loops
    if not pragma_pos and llm_pragmas:
        new_merged = []
        pi = 0
        for line in merged:
            stripped = line.lstrip()
            if pi < len(llm_pragmas) and (stripped.startswith("for") or stripped.startswith("for(")):
                indent = len(line) - len(stripped)
                new_merged.append(" " * indent + llm_pragmas[pi])
                pi += 1
            new_merged.append(line)
        merged = new_merged
    return "\n".join(merged)

def cmd_optimize(args):
    """Optimize C code with HLS pragmas."""
    with open(args.input) as f:
        code = f.read()

    print(f"Input: {args.input} ({len(code.split(chr(10)))} lines)")
    print(f"Model: {args.model}")
    print(f"Top function: {args.top}")
    print()

    prompt = f"""Optimize this HLS C code for minimum latency on Xilinx FPGA.
Use #pragma HLS: PIPELINE II=1, UNROLL (factor 4-16), ARRAY_PARTITION.
Resource budget: 80% LUT/DSP available.
Top function: {args.top}

```c
{code}
```

Output the optimized code in a ```c``` block."""

    print("Calling LLM...", end=" ", flush=True)
    resp = ollama_call(prompt, model=args.model, url=args.ollama_url)
    llm_code = extract_code(resp)

    if not llm_code:
        print("FAILED (no code block in response)")
        sys.exit(1)

    # Post-process merge (100% code safety)
    merged = merge_pragmas(code, llm_code)
    merged_pragmas = extract_pragmas(merged)

    print(f"Done! ({len(merged_pragmas)} pragmas suggested)")
    print()

    # Show pragma diff
    orig_pragmas = extract_pragmas(code)
    print("=== Pragma Changes ===")
    for i, (o, m) in enumerate(zip(orig_pragmas, merged_pragmas)):
        if o != m:
            print(f"  - {o}")
            print(f"  + {m}")
    for m in merged_pragmas[len(orig_pragmas):]:
        print(f"  + {m} (new)")
    print()

    # Output
    output = args.output or args.input.replace(".c", "_opt.c")
    with open(output, "w") as f:
        f.write(merged)
    print(f"Output: {output}")
    print(f"Code safety: 100% (only pragma lines modified)")

def cmd_evaluate(args):
    """Evaluate pragma quality against ground truth."""
    import math

    with open(args.input) as f:
        pred_code = f.read()
    with open(args.pareto) as f:
        pareto_code = f.read()

    pred_pragmas = extract_pragmas(pred_code)
    pareto_pragmas = extract_pragmas(pareto_code)

    print(f"Predicted: {len(pred_pragmas)} pragmas")
    print(f"Pareto:    {len(pareto_pragmas)} pragmas")
    print()

    # Type match
    pred_types = set()
    par_types = set()
    for p in pred_pragmas:
        if "PIPELINE" in p and "OFF" not in p: pred_types.add("PIPELINE")
        if "UNROLL" in p and "factor=1" not in p: pred_types.add("UNROLL")
        if "PARTITION" in p: pred_types.add("PARTITION")
    for p in pareto_pragmas:
        if "PIPELINE" in p and "OFF" not in p: par_types.add("PIPELINE")
        if "UNROLL" in p and "factor=1" not in p: par_types.add("UNROLL")
        if "PARTITION" in p: par_types.add("PARTITION")

    all_types = par_types | {"PIPELINE", "UNROLL", "PARTITION"}
    tm = sum(1 for t in all_types if (t in pred_types) == (t in par_types)) / len(all_types)

    print(f"Type Match: {tm:.0%}")
    print(f"  Predicted types: {pred_types}")
    print(f"  Pareto types:    {par_types}")

def cmd_info(args):
    """Show system info."""
    print("CarbonCode v0.1")
    print("HLS Pragma Optimization with Local Small Language Models")
    print()
    print("Supported models (via ollama):")
    print("  gemma4:latest    (recommended, 4.5B MoE, PFS=0.883)")
    print("  qwen2.5-coder:7b (fast, 7B dense, PFS=0.633)")
    print()
    print("Key results:")
    print("  PIE C++ optimization: 78% pass@1 (> GPT-4 69%)")
    print("  HLS pragma accuracy:  PFS=0.834 (mean)")
    print("  Vitis HLS speedup:    up to 63.3x")
    print("  Code safety:          100% (post-process merge)")
    print()
    print("GitHub: https://github.com/taiwanfifi/CarbonStack")

def main():
    parser = argparse.ArgumentParser(
        description="CarbonCode: HLS Pragma Optimization with Local LLMs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s optimize --input fir.c --top fir_filter
  %(prog)s optimize --input gemm.c --top gemm --model qwen2.5-coder:7b
  %(prog)s evaluate --input fir_opt.c --pareto fir_pareto.c
  %(prog)s info
""")

    subparsers = parser.add_subparsers(dest="command")

    # optimize
    p_opt = subparsers.add_parser("optimize", help="Optimize C code with HLS pragmas")
    p_opt.add_argument("--input", "-i", required=True, help="Input C file")
    p_opt.add_argument("--top", "-t", required=True, help="Top function name")
    p_opt.add_argument("--output", "-o", help="Output file (default: input_opt.c)")
    p_opt.add_argument("--model", "-m", default="gemma4:latest", help="Ollama model")
    p_opt.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama API URL")

    # evaluate
    p_eval = subparsers.add_parser("evaluate", help="Evaluate pragma quality")
    p_eval.add_argument("--input", "-i", required=True, help="Predicted C file")
    p_eval.add_argument("--pareto", "-p", required=True, help="Pareto-optimal C file")

    # info
    subparsers.add_parser("info", help="Show system info")

    args = parser.parse_args()

    if args.command == "optimize":
        cmd_optimize(args)
    elif args.command == "evaluate":
        cmd_evaluate(args)
    elif args.command == "info":
        cmd_info(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
