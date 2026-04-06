# CarbonStack — 完整專案概覽

## 我們在做什麼

用本地小型 AI 模型（4.5B-7B 參數），自動優化半導體 FPGA 設計。
核心價值：**完全離線、不上雲、100% 不改壞程式碼**。

### 一句話
> 工程師寫 C code → CarbonCode 3 秒建議 HLS pragma → FPGA 合成加速 2-63x

---

## 用了什麼工具

### 本地環境 (你的 Mac)
| 工具 | 用途 | 位置 |
|------|------|------|
| Python 3.11 | 所有實驗腳本 | miniforge3/envs/llama.cpp |
| Docker (OrbStack) | Bambu HLS 開源合成 | bambu-test image |
| Git | 版本控制 | taiwanfifi/CarbonStack |
| LaTeX (texlive) | 論文編譯 | paper/*/main.tex → main.pdf |
| matplotlib | 圖表生成 | paper/*/figures/ |
| asciinema | CLI demo 錄影 | presentation/demo.cast |
| Gemini API | AI 討論夥伴 | gemini-webapi + pycookiecheat |

### 雲端 GPU (Vast.ai)
| 機器 | 用途 | 模型 |
|------|------|------|
| Q_RTX_6000 (24GB) | LLM 推理 + fine-tune | gemma4, qwen2.5-coder:7b |
| (之前) RTX 4090 | 快速 A/B test | gemma4 + qwen + deepseek |

### 雲端 HLS (AWS)
| 機器 | 用途 | 工具 |
|------|------|------|
| t3.xlarge (us-east-1) | Vitis HLS 合成 | Vitis HLS v2025.2 |
| AMI: FPGA Developer | 預裝 Vivado + Vitis | 無需 license |

### 資料集
| 資料集 | 大小 | 位置 | 用途 |
|--------|------|------|------|
| ForgeHLS | 968MB, 184K designs | datasets/ForgeHLS/ | HLS pragma ground truth |
| PIE | ~4GB | carboncode/benchmarks/ | C++ 優化 benchmark |

### LLM 模型（全部透過 ollama）
| 模型 | 參數 | PFS | 用途 |
|------|------|-----|------|
| Gemma4 | 4.5B MoE | **0.645** (120 kernels) | 主力推理 |
| Qwen 2.5 Coder | 7B dense | 0.633 (5 kernels) | Fine-tune base |
| DeepSeek-R1 | 14B dense | 0.756 (3/5) | 對照組 |

---

## 跑了什麼實驗

### 核心實驗（120 kernels 規模）
| 實驗 | 結果 | 文件 |
|------|------|------|
| **120-kernel PFS evaluation** | 0.645 (capped) | check/results_100_*.json |
| **OOD generalization** | 10/10 pass | check/ood_results_*.json |
| **Factor capping** | +18.6%, 0 worse | Computed from 120-kernel data |
| **Per-type accuracy** | PARTITION 94%, PIPELINE 82%, UNROLL 56% | Same |
| **Cross-architecture** | DSP 0.847 best, Image 0.320 worst | Same |

### A/B Tests
| 比較 | 結果 | Statistically Significant? | 文件 |
|------|------|---------------------------|------|
| RAG vs zero-shot | -16.3% | 需要更多數據 | hls_pragma/phase_b |
| Chaining vs zero-shot | -8.5% | 需要更多數據 | model_ab_test/ |
| Routing+Skills vs generic | **-18.7%** | **Yes (t=-2.11)** | check/routing_multiround_*.json |
| Memory vs no memory | +4.4% but +33% fail | No (t=1.25) | check/activeagent_ab_*.json |
| Checker multiround vs cap | +0.002 | No (t=1.01) | check/checker_standalone_*.json |
| Context 0 vs 3 examples | -16% | 需要更多數據 | check/context_multi_*.json |
| **Oracle routing/RAG** | **🔄 跑中** | — | — |

### Model Comparison (5 kernels, fair pass@1)
| 模型 | PFS | 文件 |
|------|-----|------|
| Gemma4 | 0.883 | model_ab_test/hls_ab_v2_*.json |
| DeepSeek-R1 | 0.756 | Same |
| Qwen 7B | 0.633 | Same |

### Fine-tune
| 模型 | Method | PFS | 文件 |
|------|--------|-----|------|
| gemma-2-2b | LoRA SFT | 0.000 | GPU logs |
| Qwen 7B | QLoRA CoT | 0.311 | check/qwen7b_eval.json |

### Vitis HLS Synthesis (18 kernel pairs)
| Best | Worst | 文件 |
|------|-------|------|
| Sort 63.3x, DCT 53.7x | Histogram 0.25x, Viterbi 0.14x | vitis_synthesis/ |

### Iterative Refinement
| 結果 | 文件 |
|------|------|
| R0 = ceiling, feedback doesn't help | check/closedloop_*.json |

### CarbonStack 8/8 PoC
| 子項目 | 成功率 | 文件 |
|--------|--------|------|
| 全部 8 個 | 24/26 tasks | poc_results/ |

---

## 怎麼重現每個實驗

### 前置條件
```bash
# 1. Clone repo
git clone git@github.com:taiwanfifi/CarbonStack.git
cd CarbonStack

# 2. 安裝 Python 依賴
pip install ijson matplotlib

# 3. 下載 ForgeHLS (968MB)
# 放到 datasets/ForgeHLS/designs/data_of_designs_forgehls.json

# 4. 啟動 ollama (在 GPU server 上)
ollama serve &
ollama pull gemma4

# 5. 如果本地沒有 ollama，建 SSH tunnel
ssh -N -L 11434:localhost:11434 -p PORT root@ssh.vast.ai &
```

### 跑 CLI demo
```bash
python main.py info
python main.py optimize --input carboncode/hls_test/fir_worst.c --top fir_filter
```

### 跑 120-kernel evaluation
```bash
cd experiments/02_hls_pragma_prediction
python run_phase_a.py A1  # 需要 ForgeHLS 數據 + ollama
```

### 跑 Model A/B test
```bash
cd experiments/03_model_comparison
python run_model_ab.py  # 需要 ollama with gemma4 + qwen + deepseek
```

### 跑 Vitis HLS 合成
```bash
# 需要 AWS FPGA Developer AMI
ssh -i ~/Downloads/vitis-key.pem ubuntu@<AWS_IP>
# 見 docs/notes/FPGA操作過程.md
```

---

## 論文狀態

| Paper | PDF | 頁數 | 目標 |
|-------|-----|------|------|
| 1. CarbonCode HLS | ✅ 466KB | 4-5p | ICCAD/DAC |
| 2. Context Distraction | ✅ 129KB | 3p | EMNLP/ACL |
| 3. CarbonStack 8/8 | ✅ 90KB | 3p | DAC Workshop |
| 4. MoE vs Dense | ✅ 117KB | 3p | FCCM Workshop |
| 5. Carbon-Verify | ✅ 91KB | 3p | DVCon |
| 6. Carbon-ActiveAgent | ✅ 127KB | 4p | NeurIPS Workshop |

所有 PDF 在 `paper/paper{1-6}_*/main.pdf`

---

## 關鍵文件索引

```
CarbonStack/
├── main.py                          ← CLI 入口
├── README.md                        ← GitHub 首頁
├── core/
│   ├── active_agent.py              ← ActiveAgent prototype
│   └── pragma_checker.py            ← 5-rule pragma 檢查器
├── docs/
│   ├── PROJECT_OVERVIEW.md          ← 你正在看的這份
│   ├── MASTER_DATA.md               ← 數據 single source of truth
│   ├── PAPER_MATRIX.md              ← 6 篇論文規劃
│   ├── PAPER_ACTION_PLAN.md         ← 改進行動清單
│   └── PROJECT_TIMELINE.md          ← 13 週行動計畫
├── experiments/
│   ├── 02_hls_pragma_prediction/    ← HLS pragma 實驗
│   ├── 03_model_comparison/         ← Model A/B test
│   ├── 05_ablation_study/           ← Ablation
│   ├── 06_carbonstack_poc/          ← 8/8 PoC
│   ├── 07_e2e_demo/                 ← End-to-end demo
│   ├── 08_iterative_refinement/     ← Vitis-in-the-loop
│   ├── 09_finetune/                 ← LoRA fine-tune 數據
│   └── 10_ood_kernels/              ← OOD 測試 kernels
├── experiment_results/
│   ├── research_findings_log.txt    ← 66 條研究發現
│   ├── pie_benchmark/               ← PIE 結果
│   ├── hls_pragma/                  ← HLS pragma 結果
│   ├── model_ab_test/               ← Model 比較結果
│   ├── vitis_synthesis/             ← Vitis 合成報告
│   └── poc_results/                 ← PoC 結果
├── paper/
│   ├── paper1_carboncode_hls/       ← 主論文
│   ├── paper2_context_distraction/
│   ├── paper3_carbonstack/
│   ├── paper4_moe_vs_dense/
│   ├── paper5_carbon_verify/
│   └── paper6_active_agent/
└── presentation/
    ├── README_講解指南.md            ← 15 分鐘 pitch
    └── demo.cast                    ← CLI demo 錄影
```

---

## 聯絡與協作

- GitHub: https://github.com/taiwanfifi/CarbonStack
- 所有實驗數據在 experiment_results/
- 所有 LLM IO log 在各實驗的 JSON 文件中
- research_findings_log.txt 記錄了每個發現的時間、數據、結論
