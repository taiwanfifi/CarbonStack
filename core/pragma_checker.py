"""
HLS Pragma Checker: Rule-based post-processing to fix common LLM pragma errors.

Rules derived from 120-kernel failure analysis (Finding #57):
1. UNROLL/PARTITION factor must be power of 2 and <= 16
2. PIPELINE OFF should rarely appear in optimized code
3. ARRAY_PARTITION complete only for small arrays (<= 32 elements)
4. UNROLL factor should not exceed loop trip count
5. Conflicting pragmas (PIPELINE + UNROLL on same scope) need reconciliation
"""
import re


def check_and_fix(pragmas, code_context=None):
    """
    Apply all rules to a list of pragma strings.
    Returns (fixed_pragmas, fixes_applied).

    Args:
        pragmas: list of "#pragma HLS ..." strings
        code_context: optional dict with {"array_sizes": {"coeffs": 16, ...},
                                          "loop_bounds": {"j": 16, ...}}
    """
    fixed = []
    fixes = []

    for p in pragmas:
        original = p
        p_fixed = p

        # Rule 1: Cap factor at power of 2, max 16
        p_fixed = _rule_cap_factor(p_fixed)

        # Rule 2: Remove PIPELINE OFF (usually a mistake in optimization)
        p_fixed = _rule_remove_pipeline_off(p_fixed)

        # Rule 3: Check PARTITION complete vs array size
        if code_context and "array_sizes" in code_context:
            p_fixed = _rule_partition_size(p_fixed, code_context["array_sizes"])

        # Rule 4: UNROLL factor vs loop bound
        if code_context and "loop_bounds" in code_context:
            p_fixed = _rule_unroll_bound(p_fixed, code_context["loop_bounds"])

        # Rule 5: Remove duplicate pragma types
        # (handled at list level below)

        if p_fixed != original:
            fixes.append({"original": original, "fixed": p_fixed, "rules": []})

        if p_fixed:  # Rule 2 might return None
            fixed.append(p_fixed)

    # Rule 5: Deduplicate - keep best of each type
    fixed = _rule_deduplicate(fixed)

    return fixed, fixes


def _rule_cap_factor(pragma):
    """Rule 1: Factor must be power of 2 and <= 16."""
    m = re.search(r"factor\s*=\s*(\d+)", pragma)
    if m:
        val = int(m.group(1))
        if val > 16:
            # Round down to nearest power of 2 <= 16
            new_val = 16
            pragma = re.sub(r"factor\s*=\s*\d+", f"factor={new_val}", pragma)
        elif val > 0 and (val & (val - 1)) != 0:
            # Not power of 2 - round to nearest
            import math
            log2 = math.log2(val)
            new_val = 2 ** round(log2)
            new_val = min(new_val, 16)
            pragma = re.sub(r"factor\s*=\s*\d+", f"factor={new_val}", pragma)
    return pragma


def _rule_remove_pipeline_off(pragma):
    """Rule 2: PIPELINE OFF in optimized code is usually wrong.
    Replace with PIPELINE II=1."""
    if "PIPELINE" in pragma and "OFF" in pragma:
        indent = len(pragma) - len(pragma.lstrip())
        return " " * indent + "#pragma HLS PIPELINE II=1"
    return pragma


def _rule_partition_size(pragma, array_sizes):
    """Rule 3: PARTITION complete only for arrays <= 32 elements."""
    if "PARTITION" not in pragma or "complete" not in pragma:
        return pragma

    # Try to find which array
    m = re.search(r"variable\s*=\s*(\w+)", pragma)
    if m:
        var = m.group(1)
        size = array_sizes.get(var, 0)
        if size > 32:
            # Too large for complete partition - use cyclic with reasonable factor
            factor = min(8, size // 4)
            pragma = pragma.replace("complete", f"cyclic")
            if "factor" not in pragma:
                pragma += f" factor={factor}"
    return pragma


def _rule_unroll_bound(pragma, loop_bounds):
    """Rule 4: UNROLL factor should not exceed smallest loop bound."""
    if "UNROLL" not in pragma:
        return pragma

    m = re.search(r"factor\s*=\s*(\d+)", pragma)
    if m:
        factor = int(m.group(1))
        # Get smallest loop bound as upper limit
        if loop_bounds:
            min_bound = min(loop_bounds.values())
            if factor > min_bound:
                new_factor = min_bound
                # Round down to power of 2
                import math
                if new_factor > 1:
                    new_factor = 2 ** int(math.log2(new_factor))
                pragma = re.sub(r"factor\s*=\s*\d+", f"factor={new_factor}", pragma)
    return pragma


def _rule_deduplicate(pragmas):
    """Rule 5: Remove duplicate pragma types, keep most specific."""
    seen_types = {}
    for p in pragmas:
        if "PIPELINE" in p:
            key = "PIPELINE"
        elif "UNROLL" in p:
            key = "UNROLL"
        elif "PARTITION" in p:
            # Different variables = different pragmas (keep all)
            m = re.search(r"variable\s*=\s*(\w+)", p)
            key = f"PARTITION_{m.group(1)}" if m else "PARTITION"
        else:
            key = p[:30]

        if key not in seen_types:
            seen_types[key] = p
        else:
            # Keep the one with more specific parameters
            existing = seen_types[key]
            if len(p) > len(existing):
                seen_types[key] = p

    return list(seen_types.values())


def extract_code_context(code):
    """Extract array sizes and loop bounds from C code for context-aware checking."""
    context = {"array_sizes": {}, "loop_bounds": {}}

    # Find array declarations: type name[SIZE]
    for m in re.finditer(r"(\w+)\s*\[(\d+)\]", code):
        name = m.group(1)
        size = int(m.group(2))
        context["array_sizes"][name] = size

    # Find loop bounds: for (... i < N; ...)
    for m in re.finditer(r"for\s*\([^;]*;\s*\w+\s*<\s*(\w+|\d+)", code):
        bound = m.group(1)
        try:
            context["loop_bounds"][bound] = int(bound)
        except ValueError:
            # It's a variable name - try to find #define
            dm = re.search(rf"#define\s+{bound}\s+(\d+)", code)
            if dm:
                context["loop_bounds"][bound] = int(dm.group(1))

    return context


# CLI usage
if __name__ == "__main__":
    import sys

    test_pragmas = [
        "#pragma HLS UNROLL factor=1024",
        "#pragma HLS PIPELINE OFF",
        "#pragma HLS ARRAY_PARTITION variable=arr type=complete dim=1",
        "#pragma HLS UNROLL factor=7",
        "#pragma HLS PIPELINE II=1",
        "#pragma HLS PIPELINE II=2",
    ]

    test_context = {
        "array_sizes": {"arr": 256, "coeffs": 16},
        "loop_bounds": {"N": 128, "TAPS": 16},
    }

    print("=== Pragma Checker Demo ===\n")
    print("Input pragmas:")
    for p in test_pragmas:
        print(f"  {p}")

    fixed, fixes = check_and_fix(test_pragmas, test_context)

    print(f"\nFixed pragmas:")
    for p in fixed:
        print(f"  {p}")

    print(f"\nFixes applied: {len(fixes)}")
    for f in fixes:
        print(f"  {f['original']}")
        print(f"  → {f['fixed']}")
