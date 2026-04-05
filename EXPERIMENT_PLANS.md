# CarbonStack — 8 個實驗框架

> 每個實驗 = 一個子專案 = 一篇論文 = 一個產品模組
> Top-down 規劃，bottom-up 執行

---

## 工具清單（全部免費）

| 工具 | 用途 | 安裝方式 | 大小 | 平台 |
|------|------|---------|------|------|
| **Verilator** | Verilog 模擬（超快） | `brew install verilator` | ~200MB | Mac ✅ Linux ✅ |
| **Yosys** (OSS CAD Suite) | 開源合成 | GitHub releases 下載 | ~500MB | Mac ✅ Linux ✅ |
| **Vivado/Vitis HLS** | Xilinx HLS 合成驗證 | AMD 官網下載（Standard 免費版）| ~50GB | Linux only（Mac 用 Docker）|
| **Icarus Verilog** | Verilog 模擬 | `brew install icarus-verilog` | ~50MB | Mac ✅ Linux ✅ |
| **Cocotb** | Python 寫 testbench | `pip install cocotb` | ~10MB | Mac ✅ Linux ✅ |
| **GTKWave** | 波形檢視 | `brew install gtkwave` | ~30MB | Mac ✅ |
| **OpenROAD/OpenLane** | ASIC flow + timing/power | Docker image | ~5GB | Linux |

### 安裝順序建議
```
Phase 1（現在）：Verilator + Yosys + Cocotb（Mac 上 5 分鐘裝完）
Phase 2（需要 HLS 時）：Vivado on Vast.ai Linux（50GB，1 小時）
Phase 3（需要 ASIC flow）：OpenROAD/OpenLane Docker
```

---

## 實驗 #1：CarbonCode — C++ 優化引擎 ★ 已完成大部分

### 目標
用 7B 本地模型優化 C++ code，保持正確性的同時提升效能。

### 資料來源
- PIE dataset: 978 C++ 競程任務（已有）
- CarbonBench v2: 10 個自製演算法任務（已有）

### 方法
- Two-pass pipeline (correctness → optimization)
- Fallback (不展開 → 展開 → Decompose)
- 確定性驗證 (compiler + ASan + UBSan + multi-TC)

### 指標
- pass@1, pass@5（correctness）
- Speedup vs naive（performance）
- Failure taxonomy（57/36/7%）

### 需要的工具
- g++ (已有)
- Ollama + Qwen2.5-Coder-7B (已有)

### 狀態：80% 完成
- [x] Pipeline 建好
- [x] PIE 100 題 GPU 跑完 (78%)
- [x] CarbonBench Decompose (3.4x-1244x)
- [x] Failure analysis (22 題深度分析)
- [ ] Blind test (seed=99)
- [ ] Ablation study
- [ ] Paper draft

### 目標 venue：DAC/ICCAD 2026 或 MLSys

---

## 實驗 #2：Carbon-Verify — UVM Testbench 自動生成

### 目標
給定 RTL 模組的 spec/register map，自動生成 UVM testbench。

### 資料來源
- OpenCores: 開源 RTL IP（I2C, SPI, UART controller）
- VerilogEval: NVIDIA 的 Verilog benchmark（小任務）
- 自建：從 OpenCores 抽取 10-20 個模組 + 手寫 golden testbench

### 方法
1. LLM 讀 RTL spec → 生成 UVM sequence/monitor/agent
2. 用 Cocotb (Python testbench) 做第一版驗證（比 SystemVerilog 容易讓 LLM 生成）
3. CarbonCode 優化生成的 testbench
4. 跑模擬看 coverage

### 指標
- Functional coverage (%)
- Compilation success rate
- 生成 vs 人寫的 testbench 比較

### 需要的工具
- Verilator（模擬）
- Cocotb（Python testbench）
- Icarus Verilog（備用模擬器）

### 狀態：0% — 概念階段
- [ ] 下載 OpenCores 模組
- [ ] 定義 10 個 benchmark 任務
- [ ] 建 pipeline
- [ ] 跑實驗

### 目標 venue：DAC 2027

### 學術空白
**沒有 "UVM-Eval" benchmark。** 如果我們做了 = 第一個 = 高引用。

---

## 實驗 #3：Carbon-HLS — HLS C++ 生成與優化

### 目標
讓 LLM 自動選擇最佳 HLS pragma 組合，達到最優的面積/延遲/功耗。

### 資料來源
- ForgeHLS: 184K 個 HLS 設計 + 合成結果（已下載 ✅）
- HLStrans: 23K+ C→HLS 翻譯對（已下載 ✅）

### 方法
**Phase A（不需 Vivado，現在能做）：**
1. 從 ForgeHLS 抽取同一個演算法的多種 pragma 版本
2. 讓 LLM 預測哪種 pragma 組合最好（QoR prediction）
3. 用 ForgeHLS 的合成結果當 ground truth 評估

**Phase B（需要 Vivado）：**
1. LLM 生成新的 pragma 組合
2. 實際跑 Vitis HLS 合成驗證
3. 比較 LLM 選的 vs 人類選的 vs exhaustive search

### 指標
- Synthesizability rate（能不能合成成功）
- QoR: LUT, DSP, FF, BRAM 使用量
- Latency（cycle 數）
- LLM pragma vs Pareto optimal 的差距

### 需要的工具
- Phase A: 只需 Python（分析 ForgeHLS JSON）
- Phase B: Vivado/Vitis HLS（Linux, 50GB）

### 狀態：5% — dataset 已下載
- [x] ForgeHLS 下載
- [x] HLStrans 下載
- [ ] 資料探索 & 分析
- [ ] Phase A 實驗
- [ ] Vivado 安裝
- [ ] Phase B 實驗

### 目標 venue：ICCAD 2026 / DAC 2027

### 通訊連結
ForgeHLS 包含：ADPCM（通訊編解碼）、FFT（信號處理）、butterworth（濾波器）
→ 這些就是 MediaTek/Qualcomm 晶片裡的 DSP 核心

---

## 實驗 #4：Carbon-Firmware — Driver 自動生成

### 目標
給定 register map (SVD/YAML)，自動生成 C/C++ driver code。

### 資料來源
- CMSIS-SVD: ARM MCU 的 register map XML（待下載）
- Linux Kernel drivers: I2C/SPI/UART/GPIO（公開）
- Zephyr RTOS: 嵌入式 driver 程式碼（公開）

### 方法
1. Parse SVD XML → 抽取 register 定義
2. LLM 生成 HAL driver code（init, read, write, interrupt handler）
3. CarbonCode 優化生成的 driver
4. 用 QEMU 或 Renode 模擬驗證

### 指標
- Compilation success rate
- MISRA C compliance (clang-tidy 檢查)
- Binary size
- 功能正確性（模擬器驗證）

### 需要的工具
- Python（SVD 解析）
- arm-none-eabi-gcc（交叉編譯）
- QEMU 或 Renode（模擬器，免費）

### 狀態：0%
- [ ] 下載 CMSIS-SVD
- [ ] 選定 10 個 target MCU
- [ ] 建 pipeline

### 目標 venue：Embedded Systems Conference / DATE

---

## 實驗 #5：Carbon-Sim — Simulation 加速

### 目標
用 LLM 優化 cycle-accurate simulator 的 C++ 核心，加速模擬。

### 資料來源
- ForgeHLS 裡的 C code（本身就是 simulator kernel）
- CarbonBench v2（已有：matrix_mul, prefix_sum 等）
- Gem5 開源 CPU simulator 的 hotspot functions

### 方法
1. Profile simulator C++ code，找 hotspot
2. 只把 hotspot function 送給 LLM 優化
3. 重新跑 simulator，比較前後速度

### 指標
- Simulation speedup（壁鐘時間）
- Functional equivalence（輸出完全一致）
- 程式碼行數變化

### 需要的工具
- g++ + perf/gprof（profiling，已有）
- Verilator（如果是 Verilog simulator）

### 狀態：10% — CarbonBench 的 speedup 實驗算是 prototype
- [x] CarbonBench 證明概念（prefix sum 1244x）
- [ ] 在真實 simulator code 上測試
- [ ] 論文

### 目標 venue：DAC / ISCA workshop

---

## 實驗 #6：Carbon-Legacy — Legacy Code 重構

### 目標
自動把舊 C/C++ (C89/C++11) 重構成現代 C++ (C++20) + 加上安全規範 (MISRA)。

### 資料來源
- GitHub 歷史 C/C++ code（公開）
- ForgeHLS 裡有些舊風格的 C code
- OpenCores 的 C reference model

### 方法
1. 偵測舊 pattern（raw pointer, C-style cast, no RAII）
2. LLM 重構（smart pointer, range-based for, constexpr）
3. 編譯 + 測試確認行為一致
4. clang-tidy 量化改善

### 指標
- Cyclomatic complexity 變化
- MISRA violation 數量變化
- 功能正確性
- clang-tidy warning 減少量

### 需要的工具
- g++ / clang++ (已有)
- clang-tidy (可 brew install)

### 狀態：0% — 但可直接從 CarbonCode 延伸
- [ ] 收集 10 個舊 C++ 檔案
- [ ] 定義重構規則
- [ ] 跑實驗

### 目標 venue：ICSE / ASE (軟工 venue)

---

## 實驗 #7：Carbon-Translate — Python→C++ 翻譯

### 目標
解決「多對一映射」問題：Python 的 `list.append()` → 選最佳 C++ 實作。

### 資料來源
- TRACE benchmark (2026): 測翻譯正確性+效率
- MBPP (Python) → 手動配對 C++ 版本
- PIE dataset（已有 C++ ground truth）

### 方法
1. Python code → LLM 分析意圖 → 選最佳 C++ 資料結構
2. 生成 C++ code
3. 驗證正確性 + 量測效能
4. 跟 Cython/Codon 自動翻譯比較

### 指標
- Translation accuracy
- Speedup vs Python 原版
- Speedup vs Cython/Codon 自動翻譯
- 資料結構選擇正確率

### 需要的工具
- Python + g++ (已有)
- Cython / Codon (pip install)

### 狀態：0% — 但理論基礎在 concept.md 和 TRACE paper
- [ ] 建 Python→C++ 配對 dataset
- [ ] 跑翻譯實驗

### 目標 venue：ICLR 2027 / EMNLP

### concept.md 的核心洞察
66.4% 的效率問題 = 語言構造不匹配（TRACE 2026）
→ 這就是我們要解決的

---

## 實驗 #8：Carbon-Debug — 自動 Debug

### 目標
從 error log + source code 自動定位 root cause 並生成 fix patch。

### 資料來源
- Bugs2Fix dataset: GitHub 的 bug→fix commit pairs
- CVE database: 安全漏洞修復
- CarbonCode 的 fix loop（已有修復機制）

### 方法
1. Parse error log（compiler error / runtime crash / simulation fail）
2. LLM 分析 root cause
3. 生成 fix patch
4. 驗證 fix

### 指標
- Root cause localization accuracy
- Fix success rate
- Fix 是否引入新 bug

### 需要的工具
- g++ + ASan/UBSan (已有)
- CarbonCode 的 fix loop (已有)

### 狀態：10% — CarbonCode 的 R5 fix loop 算是 prototype
- [x] Fix loop 機制已有
- [ ] 獨立 benchmark
- [ ] 跟 Bugs2Fix 整合

### 目標 venue：ASE / ISSTA

---

## 執行優先順序

```
NOW（2026 Q2）：
  ★ #1 CarbonCode — blind test + paper draft
  ★ #3 Carbon-HLS Phase A — ForgeHLS 數據分析（不需 Vivado）

NEXT（2026 Q3）：
  #6 Carbon-Legacy — 從 #1 直接延伸
  #7 Carbon-Translate — 學術價值高

THEN（2026 Q4）：
  #2 Carbon-Verify — 需要 OpenCores + Cocotb
  #8 Carbon-Debug — 從 #1 延伸

LATER（2027）：
  #3 Phase B — 需要 Vivado
  #4 Carbon-Firmware — 需要 SVD + QEMU
  #5 Carbon-Sim — 需要 Gem5
```

---

## 聖杯實驗（如果全部整合）

> **Full-Stack Generation：**
> LLM 同時生成 RTL (#2) + HLS C++ (#3) + Firmware driver (#4) + UVM testbench (#2)
> → 全部一起跑 co-simulation
> → 證明 AI 能設計完整的晶片子系統
>
> **沒有人做過。做到 = NeurIPS / Nature Electronics 等級。**
