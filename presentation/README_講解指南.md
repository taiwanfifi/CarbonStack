# CarbonCode 講解指南

## 本資料夾內容

```
presentation/
├── README_講解指南.md    ← 你正在看的這份（講解流程 + 說詞）
├── demo.cast            ← CLI demo 錄影（用 asciinema play 播放）
├── comparison_table.md  ← 跟 AutoDSE/GPT-4/Human 的對比表
└── pitch_deck.md        ← 完整 pitch 內容（學術+產業+價值）
```

## 播放 Demo
```bash
asciinema play presentation/demo.cast
# 或上傳到網路：
asciinema upload presentation/demo.cast
```

---

# 講解流程（建議 15 分鐘）

## 第一部分：痛點（3 分鐘）

### 跟教授/業界說
> 「半導體設計裡，HLS（High-Level Synthesis）讓工程師用 C/C++ 寫硬體。但同一段 C code，不同的 pragma 設定，效能可以差 **30,000 倍**。工程師要花 2-3 天試各種組合才能找到好的配置。」

### 數據佐證
- ForgeHLS 資料集：184,734 筆設計，471 種演算法
- FIR filter：最差 330,753 cycles → 最佳 422 cycles = **784x 差距**
- AES encrypt：**30,468x** 差距
- 只有 **2.1%** 的配置在 Pareto 最佳前沿上

### 現有解法的問題
| 工具 | 做法 | 問題 |
|------|------|------|
| AutoDSE (UCLA, 2022) | 跑 100-500 次合成搜索 | **要 8-24 小時** |
| HARP (2023) | 用 RL 學習 pragma 策略 | 需要訓練，不能遷移 |
| GPT-4 / HLSPilot | 用雲端大模型建議 | **程式碼上雲 → 違反保密規定** |

> 「台積電、聯發科的程式碼**不能上雲**。所以 GPT-4 再強也不能用。」

---

## 第二部分：我們的做法（5 分鐘）

### 一句話
> 「CarbonCode 用一個 4.5B 的本地小模型（Gemma4），在 3 秒內建議近最佳的 pragma 配置，完全離線、100% 不改動原始程式碼。」

### 三個核心技術

**1. Post-Process Merge（100% 安全）**
> 「不是讓 AI 改你的 code。而是讓 AI 自由生成，然後我們只提取它建議的 #pragma 行，合併回原始 code。**其他程式碼一字不動。**」

這解決了業界最大的恐懼：「AI 會不會改壞我的 code？」→ **不會，100% 保證。**

**2. PFS 指標（新的評估方法）**
> 「過去評估 LLM 只看『有沒有用對 pragma 類型』（二元 yes/no）。我們提出 Pragma Fidelity Score，用 log-distance 量化『參數選得多準』。例如 UNROLL factor=8 vs 最佳 16，PFS = 0.8（差一個 2 的冪次）。」

**3. Context Distraction 發現**
> 「我們發現一個反直覺的現象：給小模型更多參考範例（RAG），準確率反而從 90% 掉到 73%。原因是小模型的注意力有限，多餘的 context 變成噪音。」

### Demo（播放錄影）
```bash
asciinema play presentation/demo.cast
```

---

## 第三部分：效果（3 分鐘）

### 核心數據

| 指標 | 我們的結果 | 對比 |
|------|----------|------|
| C++ 優化正確率 | **78% pass@1** | GPT-4: 69% pass@4 |
| Pragma 類型正確率 | **98.9%** (30 kernels) | — |
| Pragma 參數準確度 | **PFS = 0.834** | Random: 0.50 |
| Vitis 合成加速 | **中位 3.2x，最高 63.3x** | Baseline |
| 推理時間 | **3-10 秒** | AutoDSE: 8-24 小時 |
| 部署環境 | **完全離線** | GPT-4: 需要雲端 |
| 程式碼安全 | **100%** | 其他工具不保證 |

### 跟競爭者的對比

| 維度 | CarbonCode | AutoDSE | GPT-4 HLSPilot |
|------|-----------|---------|----------------|
| 模型大小 | 4.5B (本地) | N/A (搜索) | ~1.7T (雲端) |
| 一次建議時間 | **3 秒** | 8-24 小時 | ~30 秒 |
| 合成次數 | **1 次** | 100-500 次 | 1 次 |
| 離線部署 | ✅ | ✅ | ❌ |
| 程式碼安全 | ✅ 100% | ✅ | ❌ 程式碼上雲 |
| 知識遷移 | ✅ (跨 kernel) | ❌ (每次重新搜) | ✅ |
| 結果品質 | 近 Pareto (PFS=0.834) | Pareto 最佳 | ~70-80% type match |

> 「AutoDSE 找到的是最好的，但要花 24 小時。我們 3 秒給一個 83% 準的答案。工程師可以用我們的結果當起點，再花 30 分鐘微調。」

---

## 第四部分：對通訊的價值（2 分鐘）

### 通訊核心 kernel 全部涵蓋
| Kernel | 通訊用途 | 我們的 Vitis 驗證結果 |
|--------|---------|---------------------|
| FIR filter | 5G 訊號過濾 | 2050→1028 cycles (2x) |
| FFT | OFDM 調變解調 | 已合成驗證 |
| LDPC decoder | 5G 錯誤更正 | 已合成驗證 |
| Viterbi | 4G 解碼 | 18 cycles (已是最佳) |
| AES | 通訊加密 | 18→11 cycles (1.6x) |

### 對教授的意義
> 「老師的通訊專長 + 我的 AI agent 技術 = 第一個能在離線環境自動優化通訊 FPGA 設計的工具。這跟台積電、聯發科、高通的需求直接對接。」

### 對業界的價值
> 「聯發科的 5G modem 裡有上百個這樣的 kernel。每個工程師花 2 天調 pragma。如果 CarbonCode 能把這 2 天變成 3 秒 + 30 分鐘 review，整個設計週期縮短 10 倍。」

---

## 第五部分：學術定位（2 分鐘）

### 2025-2026 Survey：別人做到什麼程度

| 論文 | 年份 | 做什麼 | 跟我們的差異 |
|------|------|--------|------------|
| ChipNeMo (NVIDIA) | 2024 | 領域特化 LLM for chip design | 做 NL 任務，不做 code 優化 |
| GPT4AIGChip | 2023 | GPT-4 生成 Verilog | 用雲端，我們用本地 |
| AutoDSE (UCLA) | 2022 | 自動 pragma 搜索 | 暴力搜索，我們用 LLM 預測 |
| HARP | 2023 | RL 學 pragma | 需要訓練，我們零訓練 |
| HLSPilot | 2024 | LLM pragma 建議 | GPT-4 雲端，~70-80% match |
| **CarbonCode (ours)** | **2026** | **本地 4.5B + 100% safety** | **PFS=0.834, 離線, 3 秒** |

### 我們的學術貢獻
1. **PFS 指標** — 第一個量化 pragma 參數準確度的 metric
2. **Context Distraction Effect** — RAG 反而害小模型（反直覺發現）
3. **MoE > Dense for HLS** — 4.5B MoE 打贏 7B Dense
4. **Post-process merge** — 100% 程式碼安全的 pragma 注入方法
5. **三層驗證閉環** — ForgeHLS + Bambu + Vitis 交叉驗證

### 論文規劃
| 論文 | 目標 | 狀態 |
|------|------|------|
| Paper 1: CarbonCode HLS | ICCAD/DAC | **PDF 完成** |
| Paper 2: Context Distraction | EMNLP/ACL | 數據完整 |
| Paper 3: CarbonStack 8/8 | DAC workshop | PoC 完成 |
