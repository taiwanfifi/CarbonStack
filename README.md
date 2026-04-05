# CarbonStack

**A Unified LLM Agent Framework for Semiconductor Design Automation**

CarbonStack uses local small language models (4.5B-7B) to automate 8 semiconductor design tasks — fully offline, air-gap compatible, with 100% code safety.

## Key Results

| Benchmark | Our Result | Baseline | Improvement |
|-----------|-----------|----------|-------------|
| PIE C++ Optimization | **78% pass@1** (7B) | GPT-4: 69% pass@4 | +9% with 240x smaller model |
| HLS Pragma Accuracy | **PFS=0.834** (Gemma4) | Random: 0.50 | +67% |
| HLS Type Match | **98.9%** (30 kernels) | — | Near-perfect |
| Vitis HLS Speedup | **Up to 63.3x** | Baseline (no pragma) | Real synthesis verified |
| Code Safety | **100%** | — | Post-process merge guarantee |

## Sub-Projects (8/8 PoC Validated)

| # | Project | Task | Status |
|---|---------|------|--------|
| 1 | **CarbonCode** | C++ optimization + HLS pragma | 80% complete |
| 2 | **Carbon-Verify** | Testbench generation (Cocotb) | PoC 3/3 |
| 3 | **Carbon-HLS** | HLS code generation from description | PoC 4/5 |
| 4 | **Carbon-Firmware** | Linux driver from register spec | PoC validated |
| 5 | **Carbon-Sim** | Simulation acceleration (DPI-C) | PoC 2/2 |
| 6 | **Carbon-Legacy** | Legacy C modernization (C89→C++17) | PoC 3/3 |
| 7 | **Carbon-Translate** | Python → C++ translation | PoC 4/4 |
| 8 | **Carbon-Debug** | Automatic bug detection + fix | PoC 3/3 |

## Repository Structure

```
CarbonStack/
├── carboncode/              # Core CarbonCode pipeline (supervisor, LLM, tools)
├── experiments/             # Reproducible experiment scripts
│   ├── 01_pie_cpp_optimization/
│   ├── 02_hls_pragma_prediction/   # Phase A/B/C experiments
│   ├── 03_model_comparison/        # Gemma4 vs Qwen vs DeepSeek
│   ├── 04_vitis_synthesis/
│   ├── 05_ablation_study/
│   └── 06_carbonstack_poc/         # All 8 sub-project PoCs
├── experiment_results/      # All experiment data (JSON + logs)
│   ├── pie_benchmark/       # PIE results (78% pass@1)
│   ├── hls_pragma/          # HLS pragma prediction data
│   ├── model_ab_test/       # Model comparison + ablation
│   ├── vitis_synthesis/     # Vitis HLS reports (30+ .rpt files)
│   ├── poc_results/         # CarbonStack PoC outputs
│   └── research_findings_log.txt   # 41 chronological findings
├── docs/                    # Documentation
│   ├── PAPER_MATRIX.md      # 6 planned papers
│   └── notes/               # Operation guides (FPGA setup, etc.)
├── env/                     # Environment setup (Docker, AWS, GPU)
├── paper/                   # Paper drafts and figures
└── CarbonEval/              # Open benchmark (GitHub: taiwanfifi/CarbonEval)
```

## Quick Start

```bash
# Clone
git clone git@github.com:taiwanfifi/CarbonStack.git
cd CarbonStack

# Run HLS pragma prediction (standalone, no external data needed)
cd experiments/03_model_comparison
pip install ijson
# Start ollama with gemma4
python run_model_ab.py
```

## Models Used

| Model | Best For | PFS Score |
|-------|---------|-----------|
| **Gemma4** (4.5B MoE) | HLS pragma parameters | **0.883** |
| Qwen 2.5 Coder (7B) | Code generation speed | 0.633 |
| DeepSeek-R1 (14B) | General reasoning | 0.756 (40% fail rate) |

## Key Discoveries

1. **Context Distraction Effect**: RAG hurts small models (73% vs 90% without)
2. **MoE > Dense for HLS**: Gemma4 (4.5B active) beats Qwen (7B) by 40%
3. **Ablation**: Removing PIPELINE drops PFS 43%, PARTITION drops 39%
4. **CMPS Failure**: Cross-model pragma merge doesn't beat single model (negative result)
5. **Post-process Merge**: 100% code safety — only pragma lines are modified

## Papers

See [docs/PAPER_MATRIX.md](docs/PAPER_MATRIX.md) for 6 planned publications.

## Citation

```bibtex
@misc{carbonstack2026,
  title={CarbonStack: A Unified LLM Agent Framework for Semiconductor Design Automation},
  author={William},
  year={2026},
  url={https://github.com/taiwanfifi/CarbonStack}
}
```

## License

Research use only. Contact authors for commercial licensing.
