# Experiment 03: Model Comparison for HLS Pragma

## Goal
Fair comparison of local LLMs on HLS pragma prediction.

## Models Tested
| Model | Params (active) | Size | Speed |
|-------|----------------|------|-------|
| Gemma4 | 4.5B (MoE) | 9.6GB | 10.8s/call |
| Qwen 2.5 Coder | 7B (Dense) | 4.7GB | 3.7s/call |
| DeepSeek-R1 | 14B (Dense) | 9.0GB | 23.2s/call |

## Key Finding
Gemma4 (4.5B MoE) beats Qwen (7B Dense) by 40% on PFS despite fewer active parameters.
DeepSeek-R1 fails 40% of tasks (bad at code block formatting).

## CMPS (Cross-Model Pragma Synthesis) — Negative Result
Hypothesis: Merge Qwen's PIPELINE + Gemma4's PARTITION = better than either alone.
Result: CMPS PFS=0.690, WORSE than Gemma4 alone (0.763).
Reason: LLM output stochastic — can't reliably attribute strengths to pragma types.

## Reproduce
```bash
# Requires ollama with gemma4 + qwen2.5-coder + deepseek-r1
python run_model_ab.py    # Fair A/B test (55 LLM calls, full IO logging)
python run_cmps.py        # Cross-model merge experiment
```
