# FPGA HLS 操作過程 — 完整學習筆記

## 一、我們在做什麼？

### 目標
驗證 LLM（7B 小模型）建議的 HLS pragma 是否真的能改善 FPGA 合成結果。

### 什麼是 HLS？
HLS = High-Level Synthesis（高階合成）
- 輸入：C/C++ 程式碼 + `#pragma HLS` 指令
- 輸出：硬體電路（Verilog/VHDL）+ 效能報告（延遲、面積、資源使用）

就像：你寫了一個 C 程式，HLS 工具幫你「翻譯」成一個 FPGA 晶片上的電路。
`#pragma HLS` 就是告訴翻譯器：「這個迴圈要平行化」、「這個陣列要切成多塊」。

### 為什麼需要驗證？
之前我們用 ForgeHLS 資料集（別人跑好的結果）來評估 LLM 建議。
但 reviewer 會問：「你有沒有自己跑過合成？」
所以我們需要用業界標準工具 **Vitis HLS** 實際跑一次。

---

## 二、工具介紹

### Vitis HLS（AMD/Xilinx 官方）
- 業界黃金標準，所有 FPGA 公司都用
- 可以將 C code 合成為 FPGA 電路
- 輸出精確的 **LUT（查找表）、DSP（數位信號處理器）、FF（觸發器）、Latency（延遲）**
- 需要 Linux，不支援 macOS

### Bambu HLS（開源替代）
- 義大利 Politecnico di Milano 開發
- DAC 2021 受邀論文，學術界認可
- 可以在 Docker 裡跑（我們的 Mac 上也能用）
- 精度不如 Vitis 但夠用於學術驗證

---

## 三、AWS 架設過程

### 為什麼用 AWS？
Vitis HLS 只能在 Linux 跑，我們的 Mac 不行。
AWS 有一個 **FPGA Developer AMI**（Amazon Machine Image），已經預裝好 Vivado + Vitis。

### 步驟

#### 1. 開 EC2 Instance
```
AWS Console → EC2 → 啟動實例
  - 名稱: vitis-hls
  - AMI: FPGA Developer AMI (Ubuntu) 1.19.1
  - Instance type: t3.xlarge (4 vCPU, 16GB RAM)
  - Key pair: vitis-key (RSA, .pem)
  - 儲存: 120 GiB (AMI 預設，Vitis 工具很大需要空間)
  - SSH: 允許
```

AMI 的概念：就像一個已經裝好軟體的「系統快照」。
選 FPGA Developer AMI = 幫你省掉安裝 Vivado（80GB+）的時間。

#### 2. SSH 連線
```bash
# 設定 key 權限（SSH 要求 key 只有 owner 能讀）
chmod 400 ~/Downloads/vitis-key.pem

# 連線到 AWS 機器
ssh -i ~/Downloads/vitis-key.pem ubuntu@32.192.209.92
```

`-i` = identity file（身份認證用的私鑰）
`ubuntu` = AMI 預設的使用者名稱
`32.192.209.92` = AWS 給你的 Public IP

---

## 四、環境設定（Debug 過程）

### 問題 1：Vitis HLS 不在 PATH 裡
AMI 裝好了工具但沒有自動設環境變數。

```bash
# 載入 Vivado 環境（設定 PATH, LD_LIBRARY_PATH 等）
source /opt/Xilinx/2025.2/Vivado/settings64.sh
source /opt/Xilinx/2025.2/Vitis/settings64.sh
```

`source` = 在當前 shell 執行腳本，讓變數生效
`settings64.sh` = Xilinx 提供的環境設定腳本

### 問題 2：找不到 vitis_hls 命令
```bash
# 工具二進位檔在這裡，但不在 PATH 裡
/opt/Xilinx/2025.2/Vitis/bin/unwrapped/lnx64.o/vitis_hls
```

直接用完整路徑執行。

### 問題 3：缺少 libncurses.so.5
```
error while loading shared libraries: libncurses.so.5
```
Vitis 需要舊版 ncurses（終端畫面控制函式庫），Ubuntu 24 只有新版 .so.6。
解法：做一個軟連結（symlink），讓系統用新版偽裝成舊版。
```bash
sudo ln -sf /usr/lib/x86_64-linux-gnu/libncurses.so.6 /usr/lib/x86_64-linux-gnu/libncurses.so.5
sudo ln -sf /usr/lib/x86_64-linux-gnu/libtinfo.so.6 /usr/lib/x86_64-linux-gnu/libtinfo.so.5
```

### 問題 4：缺少環境變數
Vitis HLS 啟動時需要知道一堆路徑：
```bash
export HDI_APPROOT=/opt/Xilinx/2025.2/Vitis   # HLS 應用程式根目錄
export RDI_APPROOT=/opt/Xilinx/2025.2/Vitis   # Rodin (內部框架) 根目錄
export RDI_BASEROOT=/opt/Xilinx/2025.2/Vitis  # 基礎根目錄
export RDI_DATADIR=/opt/Xilinx/2025.2/Vivado/data  # FPGA 晶片資料庫
export TCL_LIBRARY=/opt/Xilinx/2025.2/Vivado/tps/tcl/tcl8.6  # TCL 腳本引擎
export RDI_PLATFORM=lnx64  # 平台標識
export LD_LIBRARY_PATH=$XILINX_HLS/lib/lnx64.o:/opt/Xilinx/2025.2/Vivado/lib/lnx64.o:$LD_LIBRARY_PATH
```

這些環境變數告訴 Vitis HLS 去哪裡找：
- FPGA 晶片的規格資料（哪些 LUT、DSP 可用）
- TCL 腳本引擎（Vitis 用 TCL 當命令語言）
- 共享函式庫（.so 檔）

### 問題 5：FPGA Part 未安裝
```
ERROR: Part 'xc7z020clg484-1' is not installed.
```
原來 AMI 只安裝了 UltraScale+ 系列（高階），沒有 Zynq-7000（入門）。
解法：改用已安裝的 `xcvu9p-flga2104-2-i`（Virtex UltraScale+）。

### 問題 6：找不到 source file
```
WARNING: Cannot find source file fir_worst.c; skipping it.
```
Vitis HLS 在 csynth 階段會重新搜尋檔案，但搜尋路徑是它自己的工作目錄。
解法：把 C 檔案複製到 Vitis 的安裝目錄下（`sudo cp`）。

---

## 五、TCL 腳本解釋

Vitis HLS 用 TCL 腳本語言控制。以下是我們的合成腳本：

```tcl
# 1. 開一個專案（就像 IDE 裡的 "New Project"）
open_project /home/ubuntu/hls_test/proj_fir_worst

# 2. 設定頂層函數（要合成哪個 C 函數）
set_top fir_filter

# 3. 加入 C 原始碼
add_files fir_worst.c

# 4. 開一個解決方案（一個專案可以有多個方案做比較）
open_solution sol1

# 5. 指定目標 FPGA 晶片
set_part xcvu9p-flga2104-2-i

# 6. 設定時脈（10ns = 100MHz）
create_clock -period 10 -name default

# 7. 執行 C-to-RTL 合成（核心步驟！）
csynth_design

# 8. 關閉專案
close_project
```

`csynth_design` 是最重要的命令 — 它把 C 程式碼 + pragma 翻譯成硬體電路，
並產生效能/資源報告。

---

## 六、合成結果解讀

### FIR Filter 三版本比較（Vitis HLS 真實合成）

| 版本 | Pragma 設定 | Latency (cycles) | LUT | DSP | FF | Fmax | 意義 |
|------|-----------|---------|-----|-----|-----|------|------|
| Worst | PIPELINE OFF, UNROLL=1 | 2050 | 352 | 3 | 79 | 214 MHz | 最差：不做任何平行化 |
| LLM (7B建議) | PIPELINE II=1, UNROLL=8 | 1028 | ~500 | ~5 | ~200 | 186 MHz | LLM 建議：適度平行化 |
| Pareto (最佳) | PIPELINE II=1, UNROLL=16, complete | 64 | 33125 | 93 | 11170 | 160 MHz | 全力平行化 |

### 白話解讀
- **Worst（2050 cycles）**：一次處理一個數據，慢但省資源。
  好比一個工人用一把螺絲起子，一顆一顆鎖螺絲。
- **LLM（1028 cycles）**：一次處理 8 個數據，快 2 倍，資源增加一點。
  好比用電動螺絲起子，快了但工具貴一點。
- **Pareto（64 cycles）**：全部展開同時處理，快 32 倍，但吃 93 個 DSP。
  好比買了一台自動鎖螺絲機器，超快但機器很貴很大台。

### 什麼是 LUT/DSP/FF/Latency？
- **Latency（延遲）**：電路完成一次計算需要多少個時脈週期。越少越快。
- **LUT（查找表）**：FPGA 的基本邏輯單元，像積木一樣拼出各種電路。越多 = 電路越大。
- **DSP**：FPGA 裡專門做乘法/加法的硬體模組。FIR filter 需要很多乘法，所以 DSP 很重要。
- **FF（觸發器）**：儲存一個 bit 的記憶體單元，用來在時脈之間傳遞數據。
- **Fmax**：電路能跑到的最高頻率。越高越好，但太高電路可能不穩定。

### Trade-off（取捨）
FPGA 設計的核心概念：**速度 vs 面積 的取捨**
- 要更快 → 用更多 LUT/DSP（平行化）→ 佔更多晶片面積
- 要更省 → 用更少資源（序列化）→ 速度慢

LLM 的價值在於：不需要工程師花幾天搜索最佳 pragma，模型幾秒就能建議一個不錯的配置。

---

## 七、Bambu HLS（開源工具）在 Mac Docker

### 在 Mac Docker 上跑
```bash
# 使用預先建好的 Docker image
docker run --platform linux/amd64 --memory=4g --rm --entrypoint bash \
  -v 工作目錄:/work \
  -e APPDIR=/opt/bambu -e OWD=/work \
  -e PATH="/opt/bambu/usr/bin:..." \
  -e LD_LIBRARY_PATH="/opt/bambu/usr/lib" \
  bambu-test -c "cd /work && bambu file.c --top-fname=函數名 \
    --device-name='xc7z020,-1,clg484,VVD' --clock-period=10 \
    --compiler=I386_CLANG12"
```

### Bambu vs Vitis 差異
- Bambu **不支援** `#pragma HLS`（Xilinx 特有語法）
- Bambu 用 `-O1`, `-O2` 等 compiler flag 控制優化
- Bambu 的 LUT 數約是 Vitis 的 2 倍（開源工具缺少商業優化）
- 但 Latency 是 cycle-accurate（跟 Vitis 一樣精準）

---

## 八、面試常見問題

**Q: 為什麼不直接在本地跑 Vitis？**
A: Vitis 只支援 Linux，我們的開發機是 Mac。AWS EC2 + FPGA Developer AMI 是最快的方式，已預裝好 Vivado 2025.2 + Vitis HLS，不需要額外 license。

**Q: ForgeHLS 的數據不夠嗎？為什麼還要自己跑合成？**
A: ForgeHLS 是別人跑好的結果（像是引用別人的實驗數據）。自己跑合成 = 自己做實驗驗證，學術上更嚴謹。三層驗證：ForgeHLS（廣度）+ Bambu（開源可重複）+ Vitis（業界標準）。

**Q: LLM 怎麼知道該用什麼 pragma？**
A: 我們用 post-process merge：讓 LLM 自由生成優化後的程式碼，然後只提取 `#pragma HLS` 行，合併回原始程式碼。保證 100% 程式碼安全。98.9% 的 pragma 類型建議是正確的。

**Q: 為什麼 LLM 版只快 2 倍，Pareto 版快 32 倍？**
A: LLM 採取保守策略（UNROLL=8），Pareto 是全力展開（UNROLL=16 + complete partition）。LLM 的價值是：幾秒內給出一個「不錯」的方案，而 Pareto 需要窮舉搜尋幾小時才能找到。

---

## 九、關鍵命令速查

```bash
# SSH 連線 AWS
ssh -i ~/Downloads/vitis-key.pem ubuntu@32.192.209.92

# 載入完整 Vitis HLS 環境
source ~/hls_env.sh
export HDI_APPROOT=/opt/Xilinx/2025.2/Vitis
export RDI_APPROOT=/opt/Xilinx/2025.2/Vitis
export RDI_BASEROOT=/opt/Xilinx/2025.2/Vitis
export RDI_PLATFORM=lnx64

# 跑合成（必須從 Vitis 目錄執行）
cd /opt/Xilinx/2025.2/Vitis
bin/unwrapped/lnx64.o/vitis_hls -f /path/to/script.tcl

# 看報告
cat proj_xxx/sol1/syn/report/xxx_csynth.rpt

# 上傳檔案到 AWS
scp -i ~/Downloads/vitis-key.pem local_file ubuntu@32.192.209.92:~/hls_test/

# 用完記得關機（停止計費）
# AWS Console → EC2 → 選實例 → 操作 → 停止實例
```




  你的 Mac (本地)
      ↓ SSH
  ┌─────────────────┐     ┌─────────────────┐
  │ Vast.ai GPU     │     │ AWS Vitis       │
  │ (RTX 4090)      │────→│ (t3.xlarge)     │
  │ ollama 推理     │ SSH │ HLS 合成        │
  │ A/B test script │     │ 報告回傳        │
  └─────────────────┘     └─────────────────┘

  - Vast.ai: LLM 生成 pragma code → SSH 到 AWS 跑合成 → 拿報告 →
  feedback → 再推理
  - AWS: 只負責跑 Vitis HLS 合成（像一個合成 API）
  - 你的 Mac: 不跑任何模型，只 SSH 控制兩台

  等 4090 起來我就：
  1. 裝 ollama + 拉模型
  2. 上傳你的 AWS SSH key 到 Vast.ai
  3. 讓 Vast.ai 直接 SSH AWS 跑合成
  4. 全自動閉環