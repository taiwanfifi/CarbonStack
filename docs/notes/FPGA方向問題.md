# FPGA/HLS 方向問題 — 給 William 的決策文件

## 一、我們現在在哪裡

### 已驗證的數據（全部有 Vitis HLS 真實合成）

| 實驗 | 結果 | 等級 |
|------|------|------|
| PIE C++ 優化 | 78% pass@1 (7B) > GPT-4 69% pass@4 | **A** |
| Pragma 類型判斷 | 90-99% | **A** |
| Pragma 參數準確度 (PFS) | 82% | **B+** |
| Code safety | 100% (post-process merge) | **A+** |
| Vitis 合成加速 | 中位數 2.9x，最佳 53.7x | **B+** |
| **Iterative (FIR)** | **2050 → 18 cycles = 114x** | **A+** |

### 關鍵發現
- **Context Distraction**: RAG (73%) 反而比 Zero-shot (90%) 差 — 7B reasoning > mimicry
- **Multi-stage chaining**: 分步驟問 → 參數從 1(錯) 改到 16(對)
- **Iterative refinement**: 第一輪就能達到 114x，但第二輪會過度反應

---

## 二、要從 B+ 到 A+ 需要什麼

### 我（Claude）能做的事

1. **改進 Iterative feedback 格式**
   - 加入 resource budget 限制（「DSP 不要超過 20」）
   - 用 Pareto-aware scoring（不只看 latency，也看 LUT/DSP trade-off）
   - 預期：解決 R2 過度反應問題

2. **擴大 Vitis 驗證數量**
   - 從 7 個 → 30+ 個 kernel
   - 需要你重啟 AWS，給我新 IP

3. **跟 AutoDSE 正式對比**
   - 安裝 AutoDSE（開源，UCLA 的）
   - 在同一組 kernel 上跑，比較：搜索時間、最終 latency、resource usage
   - 我們的優勢：5 次迭代 vs 1000 次隨機搜索

4. **PIE 統計強化**
   - 跑 20 次（不同 seed），計算 confidence interval
   - 本地就能做

5. **完整 Ablation study**
   - 拿掉每個組件看影響

---

## 三、需要你決定的事

### 問題 1：要不要做 Code-level Transformation？

**什麼是 code transformation（白話）：**
現在我們只改 `#pragma` 行（告訴編譯器怎麼優化），不動程式碼本身。
Code transformation 是直接改程式碼結構，例如：

```c
// 原始：一次處理一個元素
for (i = 0; i < 1024; i++)
    process(data[i]);

// Tiling 後：每次處理 32 個元素的 block
for (ii = 0; ii < 1024; ii += 32)     // outer: block 級
    for (i = ii; i < ii+32; i++)       // inner: 元素級
        process(data[i]);
```

這能讓 FPGA 更有效率地使用 on-chip memory。

**7B 模型做不到的原因：**
它不理解「為什麼 tiling 有效」（需要理解 cache line / memory bank 的物理限制）。
它會照抄語法但不會推理出正確的 tile size。

**可能的解法（需要你判斷）：**

| 方案 | 難度 | 效果 | 說明 |
|------|------|------|------|
| **A. Template library** | 中 | 中 | 預寫 5-10 個 pattern（tiling/buffering/streaming），LLM 選哪個套用 |
| **B. 更大模型** | 低 | 高 | 14B/32B 做 code transformation，7B 做 pragma |
| **C. LLVM compiler pass** | 高 | 最高 | 用 LLVM 的 Polly pass 做 tiling，LLM 做 pragma。分工 |
| **D. 不做** | 0 | 0 | 專注 pragma-only iterative，code transformation 當 future work |

**我的建議：方案 D（先不做），把 iterative pragma 做到極致。**
理由：iterative 已經證明 114x 是可能的，而且能在論文裡聲稱 "with just 5 iterations, we achieve results comparable to exhaustive DSE search." Code transformation 是第二篇論文的材料。

**但如果你想做：方案 A（template）最務實。** 我可以寫 5 個 HLS 常用 pattern：
- Loop tiling (for memory efficiency)
- Double buffering (for pipeline)
- Data streaming (for throughput)
- Ping-pong buffer (for concurrent read/write)
- Burst access (for memory bandwidth)

然後讓 LLM 分析 kernel 特性 → 選最適合的 pattern → 套用。

### 問題 2：LoRA 微調

用 ForgeHLS 的 184K 筆資料微調 7B 模型，讓它「內化」HLS pragma 知識。
- **效果預期**：PFS 從 82% → 90-95%
- **需要**：GPU（你的 Vast.ai 帳號或 AWS GPU instance）
- **時間**：training ~2-4 小時
- **風險**：可能 overfit 到 ForgeHLS 的風格

你要不要做？

---

## 四、AWS 操作備忘

### 目前狀態
- Instance: `vitis-hls` (t3.xlarge, us-east-1d)
- 狀態：運行中（建議你 Stop 省錢）
- 所有報告已 sync 到 `check/vitis_reports/`（22 份 .rpt 檔案）
- Key: `~/Downloads/vitis-key.pem`

### Stop instance
```
AWS Console → EC2 → 選 vitis-hls → 操作 → 停止實例
```
停機後只收硬碟費 ~$0.50/天。

### 重啟後
```
AWS Console → 選 vitis-hls → 操作 → 啟動實例
把新的 Public IP 告訴我
```

### 連線命令
```bash
ssh -i ~/Downloads/vitis-key.pem ubuntu@<NEW_IP>
```



  完整 A/B Test 結果

  ┌─────────────────┬──────────┬────────────────┬──────────────────────┐
  │     Method      │  Type    │      PFS       │         說明         │
  │                 │  Match   │  (參數準確度)  │                      │
  ├─────────────────┼──────────┼────────────────┼──────────────────────┤
  │ A1 (Zero-shot)  │ 90.0%    │ 0.818          │ 直接問 LLM           │
  ├─────────────────┼──────────┼────────────────┼──────────────────────┤
  │ A3 (HLS Rules)  │ 86.7%    │ 0.781          │ 給 LLM 優化規則      │
  ├─────────────────┼──────────┼────────────────┼──────────────────────┤
  │ A4 (Few-shot    │ 73.4%    │ 0.752          │ 給類似 kernel 的最佳 │
  │ RAG)            │          │                │  pragma              │
  ├─────────────────┼──────────┼────────────────┼──────────────────────┤
  │ A5 (Aggressive) │ 90.0%    │ 0.820          │ 要求 LLM 積極優化    │
  └─────────────────┴──────────┴────────────────┴──────────────────────┘

  關鍵發現

  1. A1 和 A5 並列最好 — 簡單直接的 prompt 效果最好
  2. A4 (RAG) 最差 — 給太多 context 反而困惑 7B 模型
  3. A3 (規則) 中間 — 規則有點幫助但也有干擾
  4. PFS ~0.82 — 參數準確度約 82%，「知道方向，劑量差一點」

  這跟 PIE 的發現完全一致：7B 模型的 context window 有限，information
  overload 會降低品質。


⏺ 現在已經有了非常完整的數據。讓我整理一下今天的全部成果給你：

  ---
  今日成果總結

  1. HLS Phase A（30 kernels, ForgeHLS）

  - Type Match: 98.9% (A1), 96.7% (A3)
  - PIPELINE 識別率: 100%
  - Design percentile: top 15%

  2. HLS Phase B（10 kernels, 4-way A/B test）

  - A1/A5 最好（PFS=0.82），A4 RAG 最差（0.75）
  - 核心發現：7B 模型「少即是多」，context overload 有害
  - 新指標 PFS 量化了參數準確度（82%）

  3. Vitis HLS 真實合成（7 kernels, 業界標準）

  - FIR 2x, GEMM 4.1x, Stencil 1.8x, DCT 53.7x, KMeans 11.5x
  - 中位數加速 2.9x
  - 一個失敗案例（Histogram 0.25x — 過度 partition）

  4. Bambu HLS（5 kernels, 開源驗證）

  - FIR 5.7x, Median 5.2x, DCT 1.5x

  5. AWS 環境完全搞定

  - Vitis HLS v2025.2 可跑
  - $100 免費額度
  - 操作文件寫好

  AWS instance 還在跑著。要不要我停機省錢，還是繼續跑更多 kernel？


l+o to expand)

⏺ 狀態更新

  所有數據都 sync 回來了。 你可以安全地 Stop AWS instance：

  ▎ AWS Console → EC2 → 選 vitis-hls → 操作 → 停止實例

  今天的突破發現

  FIR filter: 2050 → 18 cycles = 114x 加速！ 這是 Vitis HLS 真實驗證。

  但也發現 iterative refinement 的 feedback 設計需要改進 — LLM
  在第二輪過度反應（DSP 從 3 暴增到 93）。下一步要加入 resource budget 限制
  在 feedback 裡。

  需要你想的問題（你之前問的 FPGA方向問題.md）

  回到你的方向問題：我建議的路線是：

  1. 先靠 iterative refinement + 更好的 feedback 把 pragma-only 做到極致
  2. Code transformation 當作「如果你有決定」的加分項

  因為 iterative 已經證明 114x 是可能的（FIR），只是 feedback
  格式需要改。這個我能改。

  Code transformation（loop tiling, double
  buffering）需要你決定：要不要做？要的話用什麼策略？
