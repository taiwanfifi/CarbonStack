# Experiment Results Directory

All experiment data is organized by topic. Each JSON file contains full IO logging
(prompts, responses, scores) for reproducibility.

## Directory Structure

```
experiment_results/
├── research_findings_log.txt    ← 41 findings, chronological record of all discoveries
├── CARBONSTACK_BLUEPRINT.txt    ← Overall 8-project blueprint
├── CARBONSTACK_POC_STATUS.md    ← PoC status for all 8 sub-projects
│
├── pie_benchmark/               ← PIE C++ optimization experiments
│   ├── pie100_gpu_results.json  ← 78% pass@1 (seed=42)
│   ├── pie100_blind_seed99.json ← 74% pass@1 (blind test)
│   ├── pie100_v6_results.json   ← 70% (macro expansion variant)
│   └── ...                      ← 29 files total
│
├── hls_pragma/                  ← HLS pragma prediction experiments
│   ├── hls_phase_a_A1_*.json    ← 30 kernels, ForgeHLS ground truth
│   ├── hls_phase_a_A3_*.json    ← 30 kernels, with HLS rules
│   ├── hls_phase_b_*.json       ← 4-way prompt A/B test
│   └── ...                      ← 8 files total
│
├── model_ab_test/               ← Model comparison experiments
│   ├── hls_ab_v2_*.json         ← Fair A/B: Qwen vs Gemma4 vs DeepSeek (55 calls logged)
│   ├── cmps_results_*.json      ← Cross-Model Pragma Synthesis (negative result)
│   ├── stats_ablation_*.json    ← Multi-seed stats + ablation study
│   └── ...                      ← 5 files total
│
├── vitis_synthesis/             ← Vitis HLS real synthesis data
│   ├── vitis_synthesis_results.txt  ← Summary table
│   ├── vitis_iterative_*.json       ← Iterative refinement (FIR 2050→18 cycles)
│   ├── vitis_reports/               ← 30+ .rpt files from Vitis HLS v2025.2
│   └── bambu_synthesis_*.json       ← Bambu HLS validation
│
├── poc_results/                 ← CarbonStack sub-project PoC data
│   ├── carbon_hls_poc_*.json        ← Code generation from description
│   ├── carbon_verify_translate_*.json ← Testbench gen + Python→C++
│   ├── carbon_legacy_debug_*.json   ← Code modernization + auto debug
│   └── carbon_firmware_sim_*.json   ← Driver gen + sim acceleration
│
└── logs/                        ← Detailed logs and analysis
    ├── failed_tasks_deep_analysis.txt ← LLM I/O trace for failed tasks
    ├── EXPERIMENT_TIMELINE.txt       ← Chronological experiment record
    └── ...                           ← 11 files total
```

## Key Metrics Summary

| Experiment | Key Result |
|------------|-----------|
| PIE C++ pass@1 | 78% (7B) > GPT-4 69% (pass@4) |
| HLS Type Match | 98.9% (30 kernels) |
| HLS PFS (Gemma4) | mean=0.834, std=0.093 |
| Vitis Max Speedup | 63.3x (Bubble Sort) |
| Ablation: No PIPELINE | PFS drops 43% |
| Ablation: No PARTITION | PFS drops 39% |
| Best Model | Gemma4 (4.5B MoE) > Qwen 7B > DeepSeek-R1 14B |
| CarbonStack PoC | 8/8 sub-projects validated |
