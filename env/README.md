# Environment Setup

## Local (Mac)
```bash
# Bambu HLS via Docker (for open-source synthesis validation)
docker build -t bambu-test carboncode/hls_test/
# See docs/notes/FPGA操作過程.md for Bambu Docker run commands
```

## AWS Vitis HLS
```bash
# Instance: FPGA Developer AMI (Ubuntu) on t3.xlarge
# Vitis HLS v2025.2 pre-installed at /opt/Xilinx/2025.2/
# SSH: ssh -i ~/Downloads/vitis-key.pem ubuntu@<IP>
# See docs/notes/FPGA操作過程.md for full setup

# Environment script (run after SSH):
source ~/hls_env.sh
export HDI_APPROOT=/opt/Xilinx/2025.2/Vitis
export RDI_APPROOT=/opt/Xilinx/2025.2/Vitis
export RDI_BASEROOT=/opt/Xilinx/2025.2/Vitis
export RDI_PLATFORM=lnx64
```

## GPU (Vast.ai)
```bash
# RTX 4090 recommended for Gemma4 inference
# Install ollama:
curl -fsSL https://ollama.com/install.sh | sh
ollama serve &
ollama pull gemma4
ollama pull qwen2.5-coder:7b
```

## Datasets
- ForgeHLS (968MB): https://github.com/UCLA-VAST/ForgeHLS
  Place at: datasets/ForgeHLS/designs/data_of_designs_forgehls.json
- PIE: https://github.com/madaan/PIE
  Place at: carboncode/benchmarks/pie_integration/
