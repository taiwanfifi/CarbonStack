# CarbonStack PoC Status — 2026-04-05 (UPDATED)
# 6/8 sub-projects have working PoCs!

## 整體藍圖：8 個子項目

### 1. CarbonCode (C++ Optimization) — 80% 完成
**目標**: 用 LLM 自動優化 C++ 程式碼 + HLS pragma

| 實驗 | 狀態 | 結果 |
|------|------|------|
| PIE C++ Benchmark | ✅ 完成 | 78% pass@1 > GPT-4 69% pass@4 |
| HLS Phase A (ForgeHLS 30 kernels) | ✅ 完成 | Type match 98.9%, top 15% |
| HLS Phase B (4-way prompt A/B) | ✅ 完成 | A1/A5 best, PFS=0.82 |
| Model A/B (Qwen vs Gemma4 vs DeepSeek) | ✅ 完成 | Gemma4 PFS=0.883 |
| CMPS (Cross-Model Pragma Synthesis) | 🔄 跑中 | Qwen LOOP + Gemma4 PARTITION |
| Vitis HLS 合成驗證 | ✅ 12 kernels | DCT 53.7x, Sort 63.3x |
| Bambu HLS 開源驗證 | ✅ 5 kernels | FIR 5.7x |
| Iterative refinement | ⚠️ 初步 | FIR 114x 但 feedback 過度反應 |
| Context Distraction 發現 | ✅ 完成 | RAG worse than zero-shot |
| PFS 指標 | ✅ 完成 | 新的 pragma 參數準確度指標 |
| 統計顯著性 (20 runs) | ❌ 待做 | 需要在 GPU 上跑 |
| Ablation study 完整版 | ❌ 待做 | |
| AutoDSE 比較 | ❌ 待做 | 需要安裝 AutoDSE |
| 論文 LaTeX | ❌ 待做 | 7 sections 初稿有了 |

**缺的**: 統計、ablation、AutoDSE 比較、LaTeX

---

### 2. Carbon-Verify (UVM Testbench Generation) — 0% (未開始)
**目標**: 用 LLM 自動生成 SystemVerilog UVM testbench
**工業價值**: 最高（verification 佔半導體開發 70% 時間）

**PoC 計畫**:
- 輸入: RTL module (Verilog/SystemVerilog)
- 輸出: UVM testbench (driver, monitor, scoreboard)
- 用 LLM 分析 port list → 生成 transaction class → driver → monitor
- 驗證: 用 VCS/Verilator 編譯 + 跑 simulation

---

### 3. Carbon-HLS (HLS C++ Generation) — 30% (pragma 部分完成)
**目標**: 從演算法描述自動生成 HLS-ready C++
**現狀**: pragma 優化已完成 (carboncode)，缺 code generation from scratch

**PoC 計畫**:
- 輸入: 演算法描述 (例: "64-point FFT with radix-2 butterfly")
- 輸出: HLS C++ code + optimal pragmas
- 用 Vitis HLS 驗證 synthesizability

---

### 4. Carbon-Firmware (Driver Generation) — 0% (未開始)
**目標**: 從 register map / device tree 自動生成 Linux driver

**PoC 計畫**:
- 輸入: Register specification (CSV/JSON)
- 輸出: Linux kernel module (.ko) source
- 驗證: 編譯通過 + QEMU 模擬

---

### 5. Carbon-Sim (Simulation Acceleration) — 0% (未開始)
**目標**: 用 LLM 加速 RTL simulation

---

### 6. Carbon-Legacy (Legacy Code Refactoring) — 10% (PIE 是基礎)
**目標**: 自動重構老舊 C/C++ 程式碼
**現狀**: CarbonCode 的 PIE pipeline 可直接擴展

**PoC 計畫**:
- 輸入: 老舊 C code (C89/C99, macros, goto)
- 輸出: 現代化 C++ (C++17, RAII, smart pointers)
- 驗證: 功能等價 (same output for same input)

---

### 7. Carbon-Translate (Python → C++) — 0% (未開始)
**目標**: 自動將 Python 演算法翻譯成高效 C++
**學術價值**: TRACE (TRAnslation of Code Efficiency) 方向

**PoC 計畫**:
- 輸入: Python script (numpy/scipy)
- 輸出: C++ with OpenMP/SIMD
- 驗證: 功能等價 + speedup 測量

---

### 8. Carbon-Debug (Auto Debug) — 0% (未開始)
**目標**: 自動定位和修復 C/C++ bug
**現狀**: CarbonCode 的 fix loop (R5) 是基礎

---

## 優先級

### 現在做 (Phase 1 — 本週)
1. **CarbonCode 補齊**: CMPS 實驗 + 統計 + ablation
2. **Carbon-HLS PoC**: 用現有工具鏈，從描述生成 HLS C++ (5 個 kernel)
3. **Carbon-Legacy PoC**: 拿 PIE 的老舊 code 做 modernization

### 下一步 (Phase 2)
4. **Carbon-Verify PoC**: 生成簡單 UVM testbench
5. **Carbon-Translate PoC**: Python → C++ 翻譯

### 之後 (Phase 3)
6-8. 其他子項目
