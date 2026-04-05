"""
Carbon-ActiveAgent: Memory Pyramid + Surprise Gate for HLS Optimization.

Architecture (from ContinuousAgent + Nano-Claude fusion):
- L0 (Working): Current synthesis round data
- L1 (Episode): Digest of past optimization attempts
- L2 (Rules): Cross-kernel pragma rules learned from surprises

Inner loop: Tool-based execution (LLM → synthesize → parse report)
Outer loop: Surprise-gated learning (predict → observe → update memory)
"""
import json
import math
import os
import re
import time


class MemoryPyramid:
    """Hierarchical memory for HLS optimization knowledge."""

    def __init__(self, path="memory"):
        self.path = path
        os.makedirs(path, exist_ok=True)
        self.l0 = []  # Working memory: current round events
        self.l1 = self._load("l1_episodes.json", [])  # Episode digests
        self.l2 = self._load("l2_rules.json", [])  # Domain rules

    def _load(self, filename, default):
        fp = os.path.join(self.path, filename)
        if os.path.exists(fp):
            with open(fp) as f:
                return json.load(f)
        return default

    def _save(self, filename, data):
        fp = os.path.join(self.path, filename)
        with open(fp, "w") as f:
            json.dump(data, f, indent=2)

    def record_event(self, event):
        """L0: Record a raw event (synthesis result, LLM output, etc.)."""
        event["timestamp"] = time.time()
        self.l0.append(event)

    def compress_to_l1(self, summary):
        """Compress L0 events into an L1 episode digest."""
        self.l1.append({
            "summary": summary,
            "n_events": len(self.l0),
            "timestamp": time.time(),
        })
        # Keep last 20 episodes
        if len(self.l1) > 20:
            self.l1 = self.l1[-20:]
        self._save("l1_episodes.json", self.l1)
        self.l0 = []  # Clear working memory

    def add_rule(self, rule, evidence):
        """L2: Add a learned rule from surprise analysis."""
        self.l2.append({
            "rule": rule,
            "evidence": evidence,
            "timestamp": time.time(),
        })
        self._save("l2_rules.json", self.l2)

    def get_relevant_rules(self, kernel_description, max_rules=3):
        """Retrieve L2 rules relevant to current kernel."""
        # Simple keyword matching (could be upgraded to embedding-based)
        relevant = []
        desc_lower = kernel_description.lower()
        for rule in self.l2:
            rule_lower = rule["rule"].lower()
            # Check keyword overlap
            keywords = ["pipeline", "unroll", "partition", "array", "loop",
                        "memory", "latency", "dsp", "lut"]
            overlap = sum(1 for k in keywords if k in rule_lower and k in desc_lower)
            if overlap > 0:
                relevant.append((overlap, rule))
        relevant.sort(key=lambda x: -x[0])
        return [r[1] for r in relevant[:max_rules]]

    def format_context(self, kernel_name):
        """Format memory for LLM prompt injection."""
        lines = []
        # L1: Recent episodes
        recent = [e for e in self.l1[-5:]]
        if recent:
            lines.append("=== Past Optimization Experience ===")
            for e in recent:
                lines.append("- " + e["summary"])
        # L2: Rules
        if self.l2:
            lines.append("\n=== Learned Rules ===")
            for r in self.l2[-5:]:
                lines.append("- " + r["rule"])
        return "\n".join(lines) if lines else ""


class SurpriseGate:
    """Measures prediction error and gates learning intensity."""

    def __init__(self, threshold=0.3):
        self.threshold = threshold
        self.history = []

    def predict(self, kernel_name, pragmas, memory):
        """Predict expected latency based on memory + pragmas."""
        # Simple heuristic prediction
        has_pipeline = any("PIPELINE" in p and "OFF" not in p for p in pragmas)
        has_unroll = any("UNROLL" in p and "factor=1" not in p for p in pragmas)
        has_partition = any("PARTITION" in p for p in pragmas)

        # Base prediction: lower if more pragmas active
        score = 1.0
        if has_pipeline:
            score *= 0.3  # Pipeline typically 3x improvement
        if has_unroll:
            score *= 0.5
        if has_partition:
            score *= 0.7

        return {"expected_improvement": 1.0 - score,
                "confidence": 0.5}  # Low confidence = always learn

    def measure_surprise(self, prediction, actual_metrics, baseline_metrics):
        """Compare prediction vs actual. Return surprise level (0-1)."""
        if not actual_metrics.get("latency") or not baseline_metrics.get("latency"):
            return 1.0  # Maximum surprise if synthesis failed

        actual_improvement = 1.0 - (actual_metrics["latency"] / baseline_metrics["latency"])
        expected = prediction["expected_improvement"]

        # Surprise = absolute prediction error
        surprise = abs(actual_improvement - expected)

        self.history.append({
            "expected": expected,
            "actual": actual_improvement,
            "surprise": surprise,
            "timestamp": time.time(),
        })

        return surprise

    def should_learn(self, surprise):
        """Gate: only update memory if surprise exceeds threshold."""
        return surprise > self.threshold

    def generate_lesson(self, kernel_name, pragmas, prediction, actual, surprise):
        """Extract a lesson from a surprising outcome."""
        actual_lat = actual.get("latency", "?")
        actual_dsp = actual.get("dsp", "?")
        expected_imp = prediction["expected_improvement"]
        actual_imp = 1.0 - (actual["latency"] / actual.get("baseline_latency", actual["latency"]))

        if actual_imp > expected_imp:
            # Positive surprise: better than expected
            lesson = "Kernel '{}': pragmas {} worked BETTER than expected ({:.0%} vs {:.0%} improvement)".format(
                kernel_name, [p.split()[-1] for p in pragmas[:3]],
                actual_imp, expected_imp)
        else:
            # Negative surprise: worse than expected
            lesson = "Kernel '{}': pragmas caused WORSE result (lat={}, DSP={}). Avoid {} on this type.".format(
                kernel_name, actual_lat, actual_dsp,
                "aggressive PARTITION" if actual_dsp and int(str(actual_dsp)) > 30 else "current config")

        return lesson


class ActiveAgent:
    """
    Main agent loop combining Memory Pyramid + Surprise Gate.

    Flow:
    1. Load kernel
    2. Check memory for relevant rules
    3. LLM generates pragmas (with memory context)
    4. Predict expected outcome
    5. Synthesize (Vitis/Bambu)
    6. Measure surprise
    7. If surprised: extract lesson → update memory
    8. Repeat or move to next kernel
    """

    def __init__(self, memory_path="memory", llm_fn=None, synth_fn=None):
        self.memory = MemoryPyramid(memory_path)
        self.surprise = SurpriseGate(threshold=0.3)
        self.llm_fn = llm_fn  # function(prompt) -> response
        self.synth_fn = synth_fn  # function(code, name, top) -> metrics
        self.log = []

    def optimize_kernel(self, kernel_name, code, top_fn, max_rounds=3):
        """Run full optimization loop on one kernel."""
        print("  ActiveAgent: optimizing {}".format(kernel_name))

        # Get memory context
        memory_ctx = self.memory.format_context(kernel_name)

        # Get baseline (no optimization)
        baseline = {"latency": None}  # Would come from synthesis

        results = []
        for r in range(max_rounds):
            print("    Round {}:".format(r), end=" ")

            # Step 1: LLM generate with memory
            prompt = self._build_prompt(code, kernel_name, memory_ctx, r, results)

            if self.llm_fn:
                resp = self.llm_fn(prompt)
                llm_code = self._extract_code(resp)
            else:
                print("no LLM function configured")
                break

            if not llm_code:
                print("LLM failed")
                self.memory.record_event({"round": r, "status": "llm_failed"})
                continue

            pragmas = [l.strip() for l in llm_code.split("\n") if "#pragma HLS" in l]

            # Step 2: Predict
            prediction = self.surprise.predict(kernel_name, pragmas, self.memory)

            # Step 3: Synthesize
            if self.synth_fn:
                metrics = self.synth_fn(llm_code, "{}_r{}".format(kernel_name, r), top_fn)
            else:
                metrics = {"latency": None, "success": False}
                print("no synth function")
                break

            lat = metrics.get("latency", "?")
            print("lat={} dsp={}".format(lat, metrics.get("dsp", "?")), end=" ")

            # Step 4: Measure surprise
            if baseline.get("latency") and metrics.get("latency"):
                metrics["baseline_latency"] = baseline["latency"]
                surp = self.surprise.measure_surprise(prediction, metrics, baseline)
                print("surprise={:.2f}".format(surp), end=" ")

                # Step 5: Learn if surprised
                if self.surprise.should_learn(surp):
                    lesson = self.surprise.generate_lesson(
                        kernel_name, pragmas, prediction, metrics, surp)
                    self.memory.add_rule(lesson, {
                        "kernel": kernel_name, "round": r,
                        "latency": lat, "surprise": surp
                    })
                    print("→ LEARNED: {}".format(lesson[:80]))
                else:
                    print("→ expected")
            else:
                if not baseline.get("latency") and metrics.get("latency"):
                    baseline["latency"] = metrics["latency"]
                    print("→ baseline set")
                else:
                    print()

            # Record
            self.memory.record_event({
                "round": r, "kernel": kernel_name,
                "pragmas": pragmas, "metrics": metrics,
            })
            results.append({"round": r, "metrics": metrics, "pragmas": pragmas})

        # Compress to L1
        best = min((r["metrics"].get("latency", float("inf")) for r in results
                    if r["metrics"].get("latency")), default=None)
        summary = "{}: best_latency={}, {} rounds".format(kernel_name, best, len(results))
        self.memory.compress_to_l1(summary)

        return results

    def _build_prompt(self, code, kernel_name, memory_ctx, round_num, prev_results):
        parts = []
        if memory_ctx:
            parts.append(memory_ctx)
        parts.append("Optimize this HLS C code for minimum latency.")
        parts.append("Use PIPELINE II=1, UNROLL (factor 4-16), ARRAY_PARTITION.")
        if round_num > 0 and prev_results:
            last = prev_results[-1]
            lat = last["metrics"].get("latency", "?")
            parts.append("Previous attempt: latency={}. Try to improve.".format(lat))
        parts.append("\n```c\n{}\n```\n\nOutput optimized code in a ```c``` block.".format(code))
        return "\n".join(parts)

    def _extract_code(self, text):
        for lang in ["c", "cpp", ""]:
            m = re.search(r"```" + lang + r"\s*\n(.*?)```", text, re.DOTALL)
            if m:
                return m.group(1).strip()
        return None


# CLI for testing
if __name__ == "__main__":
    agent = ActiveAgent(memory_path="/tmp/test_memory")
    print("ActiveAgent initialized.")
    print("Memory L1:", len(agent.memory.l1), "episodes")
    print("Memory L2:", len(agent.memory.l2), "rules")
    print("\nTo run with LLM: set agent.llm_fn and agent.synth_fn")
    print("Example:")
    print('  agent.llm_fn = lambda p: ollama_call(p, model="gemma4")')
    print('  agent.synth_fn = lambda c, n, t: synthesize_on_aws(c, n, t)')
    print('  agent.optimize_kernel("fir", fir_code, "fir_filter")')
