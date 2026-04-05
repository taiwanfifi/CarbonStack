# CarbonStack Paper Matrix

Multiple papers from one research program. Each paper is independent but shares the CarbonStack framework.

## Paper 1: CarbonCode — HLS Pragma Optimization
**Status: Data complete, ready to write**
**Target: IEEE TCAD / ICCAD**

| Item | Status | Data |
|------|--------|------|
| PIE 78% > GPT-4 | ✅ | pie_benchmark/ |
| HLS type match 98.9% | ✅ | hls_pragma/ |
| PFS metric (parameter accuracy) | ✅ | model_ab_test/stats_ablation |
| Gemma4 vs Qwen vs DeepSeek | ✅ | model_ab_test/ |
| Multi-seed statistics | ✅ | model_ab_test/stats_ablation |
| Ablation (PIPELINE/PARTITION) | ✅ | model_ab_test/stats_ablation |
| Vitis HLS synthesis | ✅ | vitis_synthesis/ |
| Bambu HLS validation | ✅ | vitis_synthesis/ |
| Context Distraction finding | ✅ | hls_pragma/phase_b |
| CMPS negative result | ✅ | model_ab_test/cmps |
| AutoDSE comparison | ❌ TODO | Need to install + run |
| Post-process merge (100% safe) | ✅ | Documented in code |

**Story**: "Local 4.5B model achieves 83.4% pragma parameter accuracy on HLS kernels, validated by Vitis HLS synthesis with up to 63x speedup. We discover Context Distraction Effect: more context hurts small models."

---

## Paper 2: CarbonStack — Unified Semiconductor AI Framework  
**Status: 8/8 PoC complete, needs depth**
**Target: DAC / ICCAD (demo or workshop)**

| Item | Status | Data |
|------|--------|------|
| 8/8 sub-project PoC | ✅ | poc_results/ |
| End-to-end flow demo | ❌ TODO | Need to chain: Translate→HLS→Verify |
| Gemma4 as universal engine | ✅ | All PoCs use Gemma4 |
| Framework architecture | ❌ TODO | Need to formalize |
| Comparison with ChipNeMo/RTLCoder | ❌ TODO | Literature comparison |

**Story**: "One 4.5B MoE model handles 8 semiconductor design tasks — from Python algorithm translation to Linux driver generation — all locally deployable."

---

## Paper 3: Carbon-ActiveAgent — Active Inference for EDA
**Status: Architecture designed, needs implementation**
**Target: DAC / NeurIPS (AI for Science)**

| Item | Status | Data |
|------|--------|------|
| Memory Pyramid L0-L3 design | ✅ | In memory/project_carbon_activeagent.md |
| Surprise-gated learning design | ✅ | Designed |
| Iterative refinement PoC | ⚠️ Partial | FIR 2050→18 but feedback issues |
| Cross-kernel knowledge transfer | ❌ TODO | Need to implement + test |
| AutoDSE comparison (search efficiency) | ❌ TODO | Key selling point |
| Nano-Claude + ContinuousAgent fusion | ❌ TODO | Implementation |

**Story**: "First Active Inference agent for EDA — predicts synthesis outcomes, learns from surprises, converges to near-Pareto in 5 iterations vs 1000 for traditional DSE."

---

## Paper 4: Context Distraction in Small Language Models
**Status: Data complete, could be a short paper**
**Target: EMNLP / ACL Findings (NLP venue)**

| Item | Status | Data |
|------|--------|------|
| RAG hurts 7B (73% vs 90%) | ✅ | hls_pragma/phase_b |
| Chaining hurts Gemma4 (0.813 vs 0.883) | ✅ | model_ab_test/ |
| CMPS merge fails | ✅ | model_ab_test/cmps |
| Multi-model dual fails | ✅ | model_ab_test/ |
| Theoretical analysis | ❌ TODO | Why does this happen? |

**Story**: "We demonstrate that in-context learning degrades small model (<10B) performance on structured code generation tasks. Simple prompts + post-processing outperform RAG, chaining, and multi-model ensembles."

---

## Paper 5: Carbon-Verify — LLM for Hardware Verification
**Status: PoC only, needs depth**
**Target: DVCon / DAC**

| Item | Status | Data |
|------|--------|------|
| Cocotb testbench generation | ✅ PoC | poc_results/ |
| Assertion generation | ❌ TODO | |
| Bug detection rate | ❌ TODO | Need real bugs |
| Coverage analysis | ❌ TODO | |
| UVM generation | ❌ TODO | More complex |

**Story**: "LLM-generated testbenches that actually find bugs — bridging the verification gap in semiconductor design."

---

## Paper 6: PFS — A New Metric for HLS Pragma Evaluation
**Status: Data complete, could be a workshop paper**
**Target: FPGA workshop / FCCM**

| Item | Status | Data |
|------|--------|------|
| PFS definition (log-distance) | ✅ | In scripts |
| PFS vs type match comparison | ✅ | All experiments |
| PFS stability (multi-seed) | ✅ | stats_ablation |
| PFS ablation per pragma type | ✅ | stats_ablation |

**Story**: "We propose Pragma Fidelity Score (PFS), a fine-grained metric for evaluating LLM-generated HLS pragmas that captures parameter accuracy, not just type correctness."

---

## Priority Order

1. **Paper 1 (CarbonCode)** — Data 100% ready, highest impact
2. **Paper 4 (Context Distraction)** — Data ready, quick short paper
3. **Paper 2 (CarbonStack)** — 8/8 PoC, needs depth on 2-3 sub-projects
4. **Paper 3 (ActiveAgent)** — Most ambitious, needs implementation
5. **Paper 6 (PFS metric)** — Smallest, workshop paper
6. **Paper 5 (Verify)** — Needs most new work

## Shared Assets

All papers share:
- ForgeHLS dataset (184K designs)
- Vitis HLS v2025.2 on AWS
- Bambu HLS on Docker
- Gemma4 + Qwen models
- Post-process merge technique
- GitHub: taiwanfifi/CarbonStack
