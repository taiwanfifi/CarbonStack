# Paper Action Plan — Gemini Reviewer Feedback (2026-04-06)

All 6 papers received 3-4/10 (Reject). Common issues: sample size, no SOTA comparison, shallow analysis.

---

## Paper 1: CarbonCode HLS (4/10)
**Target: ICCAD/DAC | Current: 30 kernels, PFS=0.834**

### Must Fix
| # | Issue | Action | Effort |
|---|-------|--------|--------|
| 1 | **Sample size (30 kernels)** | Expand to 100+ from ForgeHLS | GPU: 2 hrs |
| 2 | **Data leakage concern** | Add OOD test (kernels NOT in ForgeHLS) | Write 10 custom kernels |
| 3 | **No resource constraint analysis** | Add Pareto frontier plot (LUT vs Latency) | Use existing Vitis data |
| 4 | **No fair SOTA comparison** | Literature comparison table (AutoDSE numbers from their paper) | 1 hr writing |
| 5 | **PFS ignores resource penalty** | Add adjusted PFS with resource penalty term | Modify PFS formula |
| 6 | **Missing related work** | Add GNN-DSE, VerilogEval, CodeLlama HLS papers | 1 hr literature search |

### Nice to Have
- Model size scaling curve (1B, 2B, 4.5B, 7B)
- Failure analysis table (what went wrong in the 16.6% failures)

**Estimated work: 1-2 weeks to reach 6/10 (Weak Accept)**

---

## Paper 2: Context Distraction (3/10)
**Target: EMNLP/ACL | Current: 10 kernels, 5 kernels × 2 seeds for curve**

### Must Fix
| # | Issue | Action | Effort |
|---|-------|--------|--------|
| 1 | **Only 10 kernels** | Expand to 100+ kernels (use ForgeHLS 471 algos) | GPU: 4 hrs |
| 2 | **No attention analysis** | Extract attention weights, show where model attends | Need custom code |
| 3 | **RAG implementation too simple** | Test BM25 vs embedding retrieval, vary k=1,2,3,5,10 | GPU: 2 hrs |
| 4 | **No statistical tests** | Add paired t-test, confidence intervals, p-values | 1 hr |
| 5 | **No error type analysis** | Categorize failures: syntax copy, format collapse, wrong params | 2 hrs |

### Nice to Have
- Test on non-HLS task (general code generation) to show generality
- Compare with larger models (does distraction disappear at 14B?)

**Estimated work: 2 weeks to reach 6/10**

---

## Paper 3: CarbonStack 8/8 (3/10)
**Target: DAC Workshop | Current: 24/26 PoC tasks**

### Must Fix
| # | Issue | Action | Effort |
|---|-------|--------|--------|
| 1 | **"Project report" not paper** | Rewrite as framework architecture paper with design decisions | 2 days |
| 2 | **2-5 samples per task** | Expand to 20+ per task (at least for top 3 sub-projects) | GPU: 1 day |
| 3 | **No SOTA comparison** | Compare CarbonCode vs GPT-4 on same kernels (literature numbers) | 1 hr |
| 4 | **No framework architecture diagram** | Design proper system architecture figure | 2 hrs |
| 5 | **Success = "it runs" not "it's good"** | Add quality metrics per sub-project | 1 day |

### Recommendation
**Gemini suggests: drop this paper. Focus on Paper 1 + 2 instead.**
The 8/8 breadth is impressive for a pitch deck but not for a paper.

---

## Paper 4: MoE vs Dense (4/10)
**Target: FCCM Workshop | Current: 5 kernels**

### Must Fix
| # | Issue | Action | Effort |
|---|-------|--------|--------|
| 1 | **Only 5 kernels** | Expand to 30+ kernels | GPU: 2 hrs |
| 2 | **No expert routing analysis** | Extract router_logits from Gemma4 | Need HuggingFace code |
| 3 | **DeepSeek comparison unfair** | Fix DeepSeek prompt to extract code properly | 1 hr |
| 4 | **No multi-seed stats** | Run 5+ seeds per kernel | GPU: 3 hrs |
| 5 | **"Gemma4" model spec unclear** | Verify exact model version and cite source | 30 min |

### Recommendation
**Merge into Paper 1 as a subsection rather than standalone paper.**
The 5-kernel comparison is too thin for a standalone paper.

---

## Paper 5: Carbon-Verify (3/10)
**Target: DVCon | Current: 3 modules**

### Must Fix
| # | Issue | Action | Effort |
|---|-------|--------|--------|
| 1 | **3 modules = Hello World** | Add AXI-Lite, FIFO with backpressure, FSM with corner cases | 1 day |
| 2 | **No self-debug loop** | Implement: iverilog error → feedback → LLM fix → retry | 2 hrs |
| 3 | **Oracle Problem not new** | Cite VeriGen, Chip-Chat, and frame as building on their work | 1 hr |
| 4 | **Cocotb claim without data** | Run full Cocotb experiment with compile+simulate+bug-detect rates | GPU: 4 hrs |
| 5 | **No comparison with GPT-4** | At minimum, cite GPT-4 Verilog generation success rates from literature | 1 hr |

### Recommendation
**This paper has the most potential for DVCon IF the modules are more complex.**
The "code vs spec" finding is genuinely useful for the verification community.

---

## Paper 6: ActiveAgent (4/10)
**Target: DAC/NeurIPS | Current: 3-5 kernels**

### Must Fix
| # | Issue | Action | Effort |
|---|-------|--------|--------|
| 1 | **3 kernels for iterative** | Expand to 20+ kernels | GPU + AWS: 1 day |
| 2 | **No surprise value curve** | Plot surprise over rounds, show gate triggering | Use existing data |
| 3 | **No L1 vs L2 ablation** | Test: no memory vs L1 only vs L2 only vs both | GPU: 3 hrs |
| 4 | **Fine-tune on wrong model** | Either use 7B+ base or frame 2B failure as capacity study | Rewrite section |
| 5 | **Negative results need more depth** | Analyze WHY R0 is ceiling (attention saturation? knowledge encoding?) | 1 day analysis |

### Recommendation
**Best paper for "honest negative results" track at NeurIPS workshop.**
But needs 10x more data to be convincing.

---

## Priority Order (What to fix first)

### Week 1: Data collection sprint
1. **Expand all experiments to 100+ kernels on ForgeHLS** (GPU batch job, 1 day)
2. **Write 10 custom OOD kernels** for Paper 1 data leakage test
3. **Run multi-seed (5 seeds) on all expanded experiments**

### Week 2: Analysis depth
4. **Paper 1**: Pareto frontier plot, resource-constrained PFS, failure analysis
5. **Paper 2**: Attention weight extraction, error categorization
6. **Paper 5**: Add complex modules (AXI-Lite, FSM), self-debug loop

### Week 3: Rewrite
7. **Paper 1 + 4 merge**: Combine MoE vs Dense into Paper 1 as subsection
8. **Paper 2 rewrite**: Add statistical tests, attention analysis
9. **Paper 6 rewrite**: Add surprise curves, L1/L2 ablation

### Week 4: Polish + submit
10. All papers final revision
11. Pick best 2-3 papers to submit first

---

## Revised Paper Strategy

| Paper | Keep? | Why |
|-------|-------|-----|
| **Paper 1** (HLS) | ✅ Merge with Paper 4 | Core contribution, needs data expansion |
| **Paper 2** (Distraction) | ✅ Standalone | Most novel finding, needs depth |
| Paper 3 (CarbonStack) | ❌ Drop or pitch deck only | Too broad for paper |
| Paper 4 (MoE vs Dense) | ❌ Merge into Paper 1 | Too thin alone |
| **Paper 5** (Verify) | ✅ If modules expanded | Good for DVCon |
| **Paper 6** (ActiveAgent) | ✅ NeurIPS workshop | Honest negative results |

**Focus: 3-4 papers, not 6. Quality over quantity.**
