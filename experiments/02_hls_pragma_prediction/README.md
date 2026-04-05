# Experiment 02: HLS Pragma Prediction

## Goal
Evaluate how well local LLMs predict optimal HLS pragmas for FPGA synthesis.

## Metrics
- **Type Match**: Does the LLM suggest the right pragma types? (PIPELINE/UNROLL/PARTITION)
- **PFS (Pragma Fidelity Score)**: How close are the numeric parameters? (log-distance based)

## Sub-experiments

### Phase A: ForgeHLS Ground Truth (30 kernels)
- Compare LLM-suggested pragmas against Pareto-optimal designs from ForgeHLS (184K designs)
- Methods: A1 (zero-shot), A3 (with HLS rules)
- **Result**: Type match 98.9%, design percentile top 15%

### Phase B: Prompt Strategy A/B Test (10 kernels)  
- A1: Zero-shot
- A3: HLS rules in prompt
- A4: Few-shot RAG (retrieved examples)
- A5: Aggressive optimization prompt
- **Result**: A1/A5 best (PFS=0.82), A4 (RAG) worst (0.75)
- **Finding**: Context Distraction — more context hurts small models

### Phase C: Model A/B Test (5 kernels, RTX 4090)
- Gemma4 (4.5B MoE) vs Qwen 7B vs DeepSeek-R1 14B
- Fair comparison: same inference count per group
- **Result**: Gemma4 PFS=0.883, Qwen 0.633, DeepSeek fails 40%

### Multi-seed Statistics (5 seeds × 5 kernels)
- mean PFS=0.834, std=0.093
- Most stable: DCT (std=0.027), least: stencil2d (std=0.154)

## How to Reproduce

### Requirements
- ollama with gemma4:latest and qwen2.5-coder:7b
- ForgeHLS dataset (download from: https://github.com/UCLA-VAST/ForgeHLS)
- Python 3.8+ with ijson

### Run
```bash
# Phase A (requires ForgeHLS data)
python run_phase_a.py A1  # Zero-shot, 30 kernels

# Phase B (requires ForgeHLS data)
python run_phase_b.py A1,A3,A4,A5

# Phase C (standalone, embedded kernels)
python run_model_ab.py  # Tests all available models

# Statistics + Ablation
python run_stats_ablation.py  # 5 seeds + ablation
```

## Data Files
Results are in `../../experiment_results/`:
- `hls_pragma/hls_phase_a_A1_*.json` — Phase A results
- `hls_pragma/hls_phase_b_*.json` — Phase B results
- `model_ab_test/hls_ab_v2_*.json` — Phase C (55 LLM calls logged)
- `model_ab_test/stats_ablation_*.json` — Statistics + ablation
