# Master Data Sheet — Single Source of Truth

**Last updated: 2026-04-06**

All numbers here are VERIFIED against actual experiment data files.
If a paper cites a number, it MUST match this sheet.

## Core Results (120 kernels, Gemma4, ForgeHLS)

| Metric | Value | Source File | Notes |
|--------|-------|-------------|-------|
| Raw PFS | **0.543** (std=0.275) | check/results_100_*.json | 103/120 successful |
| Capped PFS (factor≤16) | **0.645** (std=0.255) | Computed from same file | 25 improved, 0 worse |
| Type Match | **75.7%** | Same | Overall |
| PARTITION accuracy | **94%** | Same | Best pragma type |
| PIPELINE accuracy | **82%** | Same | |
| UNROLL accuracy | **56%** | Same | Worst — factor selection problem |
| Success rate | **85.8%** (103/120) | Same | 17 failed (no code block) |
| OOD generalization | **10/10** | check/ood_results_*.json | Custom kernels not in ForgeHLS |

## Cross-Architecture PFS (120 kernels, capped)

| Category | PFS | N |
|----------|-----|---|
| DSP/Filter | 0.847 | 6 |
| Control/Logic | 0.668 | 32 |
| Misc | 0.661 | 39 |
| Network/IO | 0.595 | 13 |
| Linear Algebra | 0.580 | 7 |
| Crypto | 0.460 | 3 |
| Image/Signal | 0.320 | 3 |

## Model Comparison (5 kernels, pass@1)

| Model | PFS | TM | Speed | N |
|-------|-----|----|----|---|
| Gemma4 (4.5B MoE) | **0.883** | 86.7% | 10.8s | 5 |
| DeepSeek-R1 (14B) | 0.756 | 66.7% | 23.2s | 3/5 |
| Qwen 2.5 (7B) | 0.633 | 86.7% | 3.7s | 5 |

**⚠️ NOTE: 0.883 is on 5 cherry-picked kernels. 120-kernel result is 0.645.**

## Context Distraction (10 kernels, Qwen 7B)

| Strategy | Type Match | PFS |
|----------|-----------|-----|
| A1 Zero-shot | 90.0% | 0.818 |
| A5 Aggressive | 90.0% | 0.820 |
| A3 HLS Rules | 86.7% | 0.781 |
| A4 Few-shot RAG | 73.4% | 0.752 |

## Context Length vs PFS (5 kernels × 2 seeds, Gemma4)

| N examples | Mean PFS |
|-----------|----------|
| 0 | 0.822 |
| 1 | 0.745 |
| 3 | 0.688 |
| 5 | 0.737 |

## Fine-tune Results

| Model | Method | Loss | PFS | Status |
|-------|--------|------|-----|--------|
| gemma-2-2b | LoRA SFT (50 steps) | 19→13.8 | 0.000 | Failed |
| gemma-2-2b | LoRA SFT (500 steps) | 19→7.3 | 0.000 | Failed |
| gemma-2-2b | LoRA SFT pragma-only (3 epochs) | 19→7.6 | 0.000 | Failed |
| **Qwen 7B** | **QLoRA CoT (3 epochs)** | **→0.047** | **0.311** | **Partial success** |
| Gemma4 | Zero-shot (no training) | — | 0.645* | Best approach |

*120 kernels with factor capping

## Vitis HLS Synthesis (18 kernel pairs)

| Kernel | Baseline | Optimized | Speedup |
|--------|----------|-----------|---------|
| FIR | 2050 | 1028 | 2.0x |
| GEMM | 67649 | 16387 | 4.1x |
| DCT | 537 | 10 | **53.7x** |
| Sort | 253 | 4 | **63.3x** |
| DotProd | 513 | 34 | 15.1x |
| KMeans | 770 | 67 | 11.5x |
| Reduction | 1026 | 130 | 7.9x |
| Sobel | 8191 | 3602 | 2.3x |
| MatVec | 4098 | 2050 | 2.0x |
| Stencil | 8191 | 4502 | 1.8x |
| Conv2D | 8191 | 4502 | 1.8x |
| AES | 18 | 11 | 1.6x |
| 5G FIR | — | 1036 | — |
| LDPC | — | 7 | — |
| Histogram | 258 | 1026 | **0.25x ⚠️** |
| Viterbi | 18 | 131 | **0.14x ⚠️** |
| Prefix Sum | 256 | 255 | 1.0x |

Median speedup (excl. regressions): **3.2x**

## Iterative Refinement

| Kernel | R0 | R1 | R2 | Best |
|--------|----|----|----|----|
| FIR | **18** | 64 | 2050 | **18 (R0)** |
| DCT | **34** | 514 | 258 | **34 (R0)** |
| DotProd | **257** | 257 | FAIL | **257 (R0)** |

**R0 is always the best. Iterative refinement does not improve.**

## ActiveAgent Memory A/B Test

| Condition | Mean PFS | Fail% | t-stat |
|-----------|---------|-------|--------|
| Baseline | 0.889 | 7% | — |
| With memory | 0.933 | **40%** | 1.25 (NOT significant) |

## CarbonStack 8/8 PoC

| Sub-project | Tasks | Success |
|-------------|-------|---------|
| CarbonCode | PIE+HLS | 78% pass@1 |
| Carbon-Verify | 3 modules | 3/3 compile, 0/2 bug caught |
| Carbon-HLS | 5 kernels | 4/5 generated |
| Carbon-Firmware | 1 spec | 172-line driver |
| Carbon-Sim | 2 BFMs | 2/2 DPI-C |
| Carbon-Legacy | 3 codes | 3/3 modernized |
| Carbon-Translate | 4 scripts | 4/4 with OpenMP |
| Carbon-Debug | 3 bugs | 3/3 found+fixed |
