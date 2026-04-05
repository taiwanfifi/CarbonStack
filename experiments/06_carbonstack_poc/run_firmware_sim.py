import json, time, re, urllib.request, sys
sys.stdout.reconfigure(line_buffering=True)

def call(prompt, model="gemma4:latest"):
    data = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"num_predict": 2048, "temperature": 0.3}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate",
                                data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read()).get("response", "")

def ext(text, lang="c"):
    for l in [lang, "c", "cpp", "sv", "verilog", ""]:
        m = re.search(r"```" + l + r"\s*\n(.*?)```", text, re.DOTALL)
        if m: return m.group(1).strip()
    return None

results = {"firmware": [], "sim": []}
ts = int(time.time())

# ===== CARBON-FIRMWARE PoC =====
print("=" * 60)
print("  CARBON-FIRMWARE PoC: Register Spec to Linux Driver")
print("=" * 60)

firmware_tasks = [
    {"name": "SPI Controller", "spec": {
        "device_name": "carbon_spi",
        "base_address": "0x40000000",
        "registers": [
            {"name": "CTRL", "offset": "0x00", "fields": [
                {"name": "enable", "bits": "0", "rw": "RW"},
                {"name": "mode", "bits": "2:1", "rw": "RW"},
                {"name": "irq_en", "bits": "3", "rw": "RW"}
            ]},
            {"name": "STATUS", "offset": "0x04", "fields": [
                {"name": "busy", "bits": "0", "rw": "RO"},
                {"name": "done", "bits": "1", "rw": "RO"},
                {"name": "error", "bits": "2", "rw": "RO"}
            ]},
            {"name": "DATA_TX", "offset": "0x08", "rw": "WO"},
            {"name": "DATA_RX", "offset": "0x0C", "rw": "RO"},
            {"name": "CLK_DIV", "offset": "0x10", "rw": "RW"}
        ],
        "interrupts": [{"name": "spi_done", "trigger": "STATUS.done rising edge"}]
    }},
    {"name": "GPIO Controller", "spec": {
        "device_name": "carbon_gpio",
        "base_address": "0x41000000",
        "registers": [
            {"name": "DIR", "offset": "0x00", "description": "Direction (0=in, 1=out)", "rw": "RW"},
            {"name": "OUT", "offset": "0x04", "description": "Output value", "rw": "RW"},
            {"name": "IN", "offset": "0x08", "description": "Input value", "rw": "RO"},
            {"name": "IRQ_EN", "offset": "0x0C", "description": "Interrupt enable mask", "rw": "RW"},
            {"name": "IRQ_STATUS", "offset": "0x10", "description": "Interrupt status", "rw": "RC"}
        ],
        "interrupts": [{"name": "gpio_irq", "trigger": "any enabled pin change"}]
    }},
]

firmware_prompt = """Generate a Linux kernel character device driver from this register specification.

Register Spec (JSON):
```json
{spec}
```

Requirements:
1. Use platform_driver framework (probe/remove)
2. Use ioremap for MMIO access
3. Implement file_operations: open, release, read, write, ioctl
4. Handle interrupt with request_irq / free_irq
5. Use dev_info/dev_err for logging
6. Follow Linux kernel coding style
7. Include proper error handling and cleanup

Output the complete C driver in a ```c``` block."""

for task in firmware_tasks:
    print("\nGenerating driver: " + task["name"] + "...", end=" ", flush=True)
    t0 = time.time()
    resp = call(firmware_prompt.format(spec=json.dumps(task["spec"], indent=2)))
    elapsed = time.time() - t0
    code = ext(resp, "c")
    if code:
        lines = len(code.split("\n"))
        has_ioremap = "ioremap" in code
        has_irq = "request_irq" in code or "irq" in code.lower()
        has_fops = "file_operations" in code
        has_probe = "probe" in code
        print("OK: {} lines, ioremap={}, irq={}, fops={}, probe={}, {:.1f}s".format(
            lines, has_ioremap, has_irq, has_fops, has_probe, elapsed))
        results["firmware"].append({
            "name": task["name"], "ok": True, "lines": lines,
            "has_ioremap": has_ioremap, "has_irq": has_irq,
            "has_fops": has_fops, "has_probe": has_probe,
            "code": code, "elapsed": round(elapsed, 1)
        })
    else:
        print("FAILED")
        results["firmware"].append({"name": task["name"], "ok": False, "raw": resp[:500]})

# ===== CARBON-SIM PoC =====
print("\n" + "=" * 60)
print("  CARBON-SIM PoC: Simulation Acceleration via DPI-C")
print("=" * 60)

sim_tasks = [
    {"name": "Float Matrix Multiply BFM", "sv_code": """
module matrix_bfm #(parameter N=4) (
    input clk, rst, start,
    output reg done,
    output reg [31:0] result [0:N*N-1]
);
    real A [0:N*N-1];
    real B [0:N*N-1];
    real C [0:N*N-1];
    integer i, j, k;

    always @(posedge clk) begin
        if (rst) begin
            done <= 0;
        end else if (start) begin
            // Initialize matrices
            for (i = 0; i < N*N; i++) begin
                A[i] = $urandom_range(0, 100) / 10.0;
                B[i] = $urandom_range(0, 100) / 10.0;
                C[i] = 0.0;
            end
            // Multiply (SLOW in SV!)
            for (i = 0; i < N; i++)
                for (j = 0; j < N; j++)
                    for (k = 0; k < N; k++)
                        C[i*N+j] = C[i*N+j] + A[i*N+k] * B[k*N+j];
            // Convert to fixed point
            for (i = 0; i < N*N; i++)
                result[i] <= $rtoi(C[i] * 256.0);
            done <= 1;
        end
    end
endmodule"""},
    {"name": "CRC Check BFM", "sv_code": """
module crc_checker (
    input clk, rst,
    input [7:0] data_in,
    input data_valid,
    output reg [31:0] crc_out,
    output reg crc_valid
);
    reg [31:0] crc;
    integer i;
    reg [31:0] poly = 32'hEDB88320;

    always @(posedge clk) begin
        if (rst) begin
            crc <= 32'hFFFFFFFF;
            crc_valid <= 0;
        end else if (data_valid) begin
            crc_valid <= 0;
            // Bit-by-bit CRC (VERY SLOW in simulation)
            for (i = 0; i < 8; i++) begin
                if ((crc[0] ^ data_in[i]) == 1'b1)
                    crc <= (crc >> 1) ^ poly;
                else
                    crc <= crc >> 1;
            end
        end else begin
            crc_out <= ~crc;
            crc_valid <= 1;
        end
    end
endmodule"""},
]

sim_prompt = """You are a verification engineer optimizing simulation speed.
This SystemVerilog BFM has computation-heavy sections that are slow in simulation.

SV Code:
```systemverilog
{sv_code}
```

Task:
1. Identify the computation-heavy sections that slow down simulation
2. Rewrite the module to use DPI-C calls for those sections
3. Generate the corresponding C function implementation

Output:
## Analysis
[explain what's slow and why DPI-C helps]

## Modified SystemVerilog (with DPI-C imports)
```systemverilog
[modified SV code]
```

## C Implementation
```c
[DPI-C function implementation]
```"""

for task in sim_tasks:
    print("\nOptimizing: " + task["name"] + "...", end=" ", flush=True)
    t0 = time.time()
    resp = call(sim_prompt.format(sv_code=task["sv_code"]))
    elapsed = time.time() - t0

    sv_code = ext(resp, "systemverilog") or ext(resp, "sv") or ext(resp, "verilog")
    c_code = ext(resp, "c")
    has_dpi = 'import "DPI-C"' in resp or "DPI" in resp
    has_analysis = "slow" in resp.lower() or "bottleneck" in resp.lower() or "heavy" in resp.lower()

    print("DPI={}, analysis={}, SV={}, C={}, {:.1f}s".format(
        has_dpi, has_analysis,
        len(sv_code.split("\n")) if sv_code else 0,
        len(c_code.split("\n")) if c_code else 0,
        elapsed))

    results["sim"].append({
        "name": task["name"], "ok": True,
        "has_dpi": has_dpi, "has_analysis": has_analysis,
        "sv_lines": len(sv_code.split("\n")) if sv_code else 0,
        "c_lines": len(c_code.split("\n")) if c_code else 0,
        "sv_code": sv_code[:2000] if sv_code else None,
        "c_code": c_code[:2000] if c_code else None,
        "analysis": resp[:2000],
        "elapsed": round(elapsed, 1)
    })

# Summary
print("\n" + "=" * 60)
print("  SUMMARY")
print("=" * 60)
f_ok = [r for r in results["firmware"] if r.get("ok")]
s_ok = [r for r in results["sim"] if r.get("ok")]
print("Carbon-Firmware: {}/{} drivers generated".format(len(f_ok), len(results["firmware"])))
if f_ok:
    print("  All have ioremap: {}".format(all(r.get("has_ioremap") for r in f_ok)))
    print("  All have IRQ: {}".format(all(r.get("has_irq") for r in f_ok)))
    print("  All have file_ops: {}".format(all(r.get("has_fops") for r in f_ok)))
print("Carbon-Sim: {}/{} optimized".format(len(s_ok), len(results["sim"])))
if s_ok:
    print("  All have DPI-C: {}".format(all(r.get("has_dpi") for r in s_ok)))
    print("  All have analysis: {}".format(all(r.get("has_analysis") for r in s_ok)))

outf = "/root/carbon_firmware_sim_{}.json".format(ts)
with open(outf, "w") as f:
    json.dump(results, f, indent=2)
print("Saved: " + outf)
