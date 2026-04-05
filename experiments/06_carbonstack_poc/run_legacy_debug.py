import json, time, re, urllib.request, sys
sys.stdout.reconfigure(line_buffering=True)

def call(prompt, model="gemma4:latest"):
    data = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": {"num_predict": 2048, "temperature": 0.3}}).encode()
    req = urllib.request.Request("http://localhost:11434/api/generate",
                                data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read()).get("response", "")

def ext(text):
    for l in ["c", "cpp", ""]:
        m = re.search(r"```" + l + r"\s*\n(.*?)```", text, re.DOTALL)
        if m: return m.group(1).strip()
    return None

results = {"legacy": [], "debug": []}
ts = int(time.time())

# ===== CARBON-LEGACY PoC: Modernize old C code =====
print("=" * 60)
print("  CARBON-LEGACY PoC: Modernize Old C Code")
print("=" * 60)

legacy_tasks = [
    {"name": "goto_to_structured", "old_code": """
#include <stdio.h>
int process(int* data, int n) {
    int i = 0, sum = 0, max = -9999;
    loop_start:
    if (i >= n) goto done;
    sum += data[i];
    if (data[i] > max) max = data[i];
    i++;
    goto loop_start;
    done:
    if (sum < 0) goto error;
    return max;
    error:
    return -1;
}"""},
    {"name": "macro_to_inline", "old_code": """
#define MAX(a,b) ((a)>(b)?(a):(b))
#define MIN(a,b) ((a)<(b)?(a):(b))
#define CLAMP(x,lo,hi) MIN(MAX(x,lo),hi)
#define ABS(x) ((x)<0?-(x):(x))
#define SWAP(a,b,t) do{t=a;a=b;b=t;}while(0)
#define SQR(x) ((x)*(x))

void process(int* arr, int n) {
    int i, j, tmp;
    for(i=0;i<n;i++) arr[i] = CLAMP(arr[i], 0, 255);
    for(i=0;i<n-1;i++)
        for(j=0;j<n-1-i;j++)
            if(arr[j]>arr[j+1]) SWAP(arr[j],arr[j+1],tmp);
}"""},
    {"name": "c89_to_modern", "old_code": """
void matrix_op(a, b, c, n)
    double *a, *b, *c;
    int n;
{
    register int i, j, k;
    double temp;
    for (i = 0; i < n; i++)
        for (j = 0; j < n; j++) {
            temp = 0.0;
            for (k = 0; k < n; k++)
                temp += *(a + i*n + k) * *(b + k*n + j);
            *(c + i*n + j) = temp;
        }
}"""},
]

legacy_prompt = """Modernize this old C code to clean, modern C++17.

Old code:
```c
{code}
```

Requirements:
1. Replace goto with structured control flow (loops, if/else)
2. Replace macros with inline functions or constexpr
3. Use modern C++ features (auto, range-for, std::array, const)
4. Keep the same functionality (functionally equivalent)
5. Add const correctness
6. Use meaningful variable names

Output the modernized C++ code in a ```cpp``` block."""

for task in legacy_tasks:
    print("\nModernizing: " + task["name"] + "...", end=" ", flush=True)
    t0 = time.time()
    resp = call(legacy_prompt.format(code=task["old_code"]))
    elapsed = time.time() - t0
    code = ext(resp)
    if code:
        lines = len(code.split("\n"))
        has_const = "const" in code
        has_auto = "auto" in code
        no_goto = "goto" not in code
        no_macro = "#define" not in code
        print("OK: {} lines, const={}, auto={}, no_goto={}, no_macro={}, {:.1f}s".format(
            lines, has_const, has_auto, no_goto, no_macro, elapsed))
        results["legacy"].append({"name": task["name"], "ok": True, "lines": lines,
                                  "has_const": has_const, "no_goto": no_goto,
                                  "no_macro": no_macro, "code": code, "elapsed": round(elapsed, 1)})
    else:
        print("FAILED")
        results["legacy"].append({"name": task["name"], "ok": False})

# ===== CARBON-DEBUG PoC: Find and fix bugs =====
print("\n" + "=" * 60)
print("  CARBON-DEBUG PoC: Auto Bug Detection and Fix")
print("=" * 60)

debug_tasks = [
    {"name": "buffer_overflow", "buggy": """
void copy_string(char* dest, const char* src) {
    int i = 0;
    while (src[i] != '\\0') {
        dest[i] = src[i];
        i++;
    }
    // Missing null terminator!
}

void process(const char* input) {
    char buffer[16];
    copy_string(buffer, input);  // No bounds checking!
}"""},
    {"name": "use_after_free", "buggy": """
#include <stdlib.h>
typedef struct { int x, y; } Point;

Point* create_point(int x, int y) {
    Point* p = (Point*)malloc(sizeof(Point));
    p->x = x; p->y = y;
    return p;
}

int distance(Point* a, Point* b) {
    free(a);  // Bug: freeing before use
    return (a->x - b->x) * (a->x - b->x) + (a->y - b->y) * (a->y - b->y);
}"""},
    {"name": "integer_overflow", "buggy": """
int factorial(int n) {
    int result = 1;
    for (int i = 2; i <= n; i++)
        result *= i;  // Will overflow for n > 12
    return result;
}

int sum_array(int* arr, int n) {
    int sum = 0;
    for (int i = 0; i <= n; i++)  // Off-by-one: should be < n
        sum += arr[i];
    return sum;
}"""},
]

debug_prompt = """You are a security-focused code reviewer. This C code has bugs.

Buggy code:
```c
{code}
```

Tasks:
1. List ALL bugs found (buffer overflow, use-after-free, integer overflow, off-by-one, etc.)
2. Explain each bug's severity and potential exploit
3. Provide the FIXED version of the code

Output format:
## Bugs Found
- Bug 1: ...
- Bug 2: ...

## Fixed Code
```c
[fixed code here]
```"""

for task in debug_tasks:
    print("\nDebugging: " + task["name"] + "...", end=" ", flush=True)
    t0 = time.time()
    resp = call(debug_prompt.format(code=task["buggy"]))
    elapsed = time.time() - t0
    code = ext(resp)
    bugs_found = len(re.findall(r"(?:Bug|bug|Issue|issue|Vulnerability)\s*\d*\s*:", resp))
    if not bugs_found:
        bugs_found = len(re.findall(r"^[-*]\s+", resp, re.MULTILINE))
    has_fix = code is not None
    print("Found {} bugs, fix={}, {:.1f}s".format(bugs_found, has_fix, elapsed))
    results["debug"].append({
        "name": task["name"], "ok": True,
        "bugs_found": bugs_found, "has_fix": has_fix,
        "fixed_code": code[:2000] if code else None,
        "analysis": resp[:2000], "elapsed": round(elapsed, 1)
    })

# Summary
print("\n" + "=" * 60)
print("  SUMMARY")
print("=" * 60)
l_ok = [r for r in results["legacy"] if r.get("ok")]
d_ok = [r for r in results["debug"] if r.get("ok")]
print("Carbon-Legacy:  {}/{} modernized".format(len(l_ok), len(results["legacy"])))
if l_ok:
    print("  All no_goto: {}".format(all(r.get("no_goto") for r in l_ok)))
    print("  All no_macro: {}".format(all(r.get("no_macro") for r in l_ok)))
print("Carbon-Debug:   {}/{} analyzed".format(len(d_ok), len(results["debug"])))
if d_ok:
    print("  Avg bugs found: {:.1f}".format(sum(r["bugs_found"] for r in d_ok) / len(d_ok)))
    print("  All have fix: {}".format(all(r.get("has_fix") for r in d_ok)))

outf = "/root/carbon_legacy_debug_{}.json".format(ts)
with open(outf, "w") as f:
    json.dump(results, f, indent=2)
print("Saved: " + outf)
