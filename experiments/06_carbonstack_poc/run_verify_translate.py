import json, time, re, urllib.request, sys
sys.stdout.reconfigure(line_buffering=True)

def call(prompt, model="gemma4:latest"):
    data = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"num_predict": 2048, "temperature": 0.3}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate",
                                data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read()).get("response", "")

def ext(text, lang="python"):
    for l in [lang, "py", "sv", "verilog", "c", "cpp", ""]:
        m = re.search(r"```" + l + r"\s*\n(.*?)```", text, re.DOTALL)
        if m: return m.group(1).strip()
    return None

results = {"verify": [], "translate": []}
ts = int(time.time())

# ===== CARBON-VERIFY PoC =====
print("=" * 60)
print("  CARBON-VERIFY PoC: Generate Testbenches")
print("=" * 60)

verify_tasks = [
    {
        "name": "FIFO Buffer",
        "verilog": """module fifo #(parameter DEPTH=8, WIDTH=8) (
    input clk, rst, wr_en, rd_en,
    input [WIDTH-1:0] data_in,
    output reg [WIDTH-1:0] data_out,
    output full, empty
);
    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [$clog2(DEPTH):0] count;
    reg [$clog2(DEPTH)-1:0] wr_ptr, rd_ptr;
    assign full = (count == DEPTH);
    assign empty = (count == 0);
    always @(posedge clk or posedge rst) begin
        if (rst) begin count<=0; wr_ptr<=0; rd_ptr<=0; end
        else begin
            if (wr_en && !full) begin mem[wr_ptr]<=data_in; wr_ptr<=wr_ptr+1; count<=count+1; end
            if (rd_en && !empty) begin data_out<=mem[rd_ptr]; rd_ptr<=rd_ptr+1; count<=count-1; end
        end
    end
endmodule""",
    },
    {
        "name": "Simple ALU",
        "verilog": """module alu (
    input [7:0] a, b,
    input [1:0] op,
    output reg [7:0] result,
    output zero
);
    assign zero = (result == 0);
    always @(*) begin
        case (op)
            2'b00: result = a + b;
            2'b01: result = a - b;
            2'b10: result = a & b;
            2'b11: result = a | b;
        endcase
    end
endmodule""",
    },
    {
        "name": "Shift Register",
        "verilog": """module shift_reg #(parameter N=8) (
    input clk, rst, load, shift,
    input [N-1:0] data_in,
    output [N-1:0] data_out,
    output serial_out
);
    reg [N-1:0] reg_data;
    assign data_out = reg_data;
    assign serial_out = reg_data[N-1];
    always @(posedge clk or posedge rst) begin
        if (rst) reg_data <= 0;
        else if (load) reg_data <= data_in;
        else if (shift) reg_data <= {reg_data[N-2:0], 1'b0};
    end
endmodule""",
    },
]

verify_prompt = """You are a hardware verification engineer. Given this Verilog module, generate a Python Cocotb testbench.

Module:
```verilog
{verilog}
```

Requirements:
1. Import cocotb and cocotb.triggers
2. Write at least 3 test cases covering normal operation, edge cases, and reset
3. Use assert statements to check correctness
4. Add clock generation
5. Include comments explaining each test

Output the complete Python cocotb testbench in a ```python``` block."""

for task in verify_tasks:
    print("\nGenerating testbench for: " + task["name"] + "...", end=" ", flush=True)
    t0 = time.time()
    resp = call(verify_prompt.format(verilog=task["verilog"]))
    elapsed = time.time() - t0
    code = ext(resp, "python")
    if code:
        lines = len(code.split("\n"))
        has_cocotb = "cocotb" in code
        has_assert = "assert" in code
        n_tests = len(re.findall(r"async def test_", code))
        print("OK: {} lines, {} tests, cocotb={}, assert={}, {:.1f}s".format(
            lines, n_tests, has_cocotb, has_assert, elapsed))
        results["verify"].append({
            "name": task["name"], "ok": True, "lines": lines,
            "n_tests": n_tests, "has_cocotb": has_cocotb, "has_assert": has_assert,
            "code": code, "elapsed": round(elapsed, 1)
        })
    else:
        print("FAILED ({:.1f}s)".format(time.time() - t0))
        results["verify"].append({"name": task["name"], "ok": False, "raw": resp[:500]})

# ===== CARBON-TRANSLATE PoC =====
print("\n" + "=" * 60)
print("  CARBON-TRANSLATE PoC: Python to C++")
print("=" * 60)

translate_tasks = [
    {
        "name": "Matrix Multiply",
        "python": """import numpy as np
def matmul(A, B):
    n = A.shape[0]
    C = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            for k in range(n):
                C[i][j] += A[i][k] * B[k][j]
    return C""",
    },
    {
        "name": "Moving Average Filter",
        "python": """def moving_average(data, window=5):
    result = []
    for i in range(len(data) - window + 1):
        avg = sum(data[i:i+window]) / window
        result.append(avg)
    return result""",
    },
    {
        "name": "Bubble Sort",
        "python": """def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(n - i - 1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]
    return arr""",
    },
    {
        "name": "Histogram",
        "python": """def histogram(data, n_bins=256):
    hist = [0] * n_bins
    for val in data:
        idx = min(val, n_bins - 1)
        hist[idx] += 1
    return hist""",
    },
]

translate_prompt = """Translate this Python code to high-performance C++.

Python:
```python
{python}
```

Requirements:
1. Use fixed-size arrays (no std::vector for performance-critical data)
2. Add OpenMP pragmas for parallelism where beneficial
3. Use const references for input parameters
4. Keep the same function signature logic
5. Make it compilable with g++ -O2 -fopenmp

Output the C++ code in a ```cpp``` block."""

for task in translate_tasks:
    print("\nTranslating: " + task["name"] + "...", end=" ", flush=True)
    t0 = time.time()
    resp = call(translate_prompt.format(python=task["python"]))
    elapsed = time.time() - t0
    code = ext(resp, "cpp") or ext(resp, "c")
    if code:
        lines = len(code.split("\n"))
        has_omp = "omp" in code.lower()
        has_const = "const" in code
        print("OK: {} lines, OpenMP={}, const={}, {:.1f}s".format(
            lines, has_omp, has_const, elapsed))
        results["translate"].append({
            "name": task["name"], "ok": True, "lines": lines,
            "has_openmp": has_omp, "has_const": has_const,
            "code": code, "elapsed": round(elapsed, 1)
        })
    else:
        print("FAILED ({:.1f}s)".format(time.time() - t0))
        results["translate"].append({"name": task["name"], "ok": False, "raw": resp[:500]})

# Summary
print("\n" + "=" * 60)
print("  SUMMARY")
print("=" * 60)
v_ok = [r for r in results["verify"] if r["ok"]]
t_ok = [r for r in results["translate"] if r["ok"]]
print("Carbon-Verify:    {}/{} testbenches generated".format(len(v_ok), len(results["verify"])))
if v_ok:
    print("  Avg tests per TB: {:.1f}".format(sum(r["n_tests"] for r in v_ok) / len(v_ok)))
print("Carbon-Translate: {}/{} translations".format(len(t_ok), len(results["translate"])))
if t_ok:
    print("  Avg lines: {:.0f}".format(sum(r["lines"] for r in t_ok) / len(t_ok)))

outf = "/root/carbon_verify_translate_{}.json".format(ts)
with open(outf, "w") as f:
    json.dump(results, f, indent=2)
print("Saved: " + outf)
