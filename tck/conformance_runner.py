"""conformance_runner.py — Silent Timeout Protocol TCK (conformance test kit).

Runs over a JSONL file of probe records and reports the highest conformance
level achieved (L0 / L1 / L2) per SPEC v0.1 section 7.

Stdlib only (zero dependencies): structural checks are equivalent to
schema/signal.schema.json but implemented inline so the TCK runs anywhere.

Usage:
    python conformance_runner.py <records.jsonl>

Exit codes: 0 = conformant (>= L0), 1 = non-conformant, 2 = usage error.
"""

import json
import re
import sys

BUCKETS = {"boot", "tools", "memory", "loop", "guardrails"}
FACES = {"idle", "done", "measured", "pass"}
SIGNAL_FIELDS = ["first_signal", "window", "window_status", "masquerade_face", "verdict_rule"]
ABSOLUTE_MARKERS = ("absolute", "not a calibration point")
ABSOLUTE_WINDOW_STATUS = ("absolute, not a calibration point",)


def _is_nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def check_row_L0(row):
    """L0: identity + bucket + failure_mode + non-empty expected."""
    errs = []
    for f in ("id", "failure_mode", "expected"):
        if not _is_nonempty_str(row.get(f)):
            errs.append(f"missing/empty '{f}'")
    if row.get("category") not in BUCKETS:
        errs.append(f"invalid bucket '{row.get('category')}'")
    if row.get("failure_mode") != "silent-timeout":
        errs.append(f"failure_mode must be 'silent-timeout', got '{row.get('failure_mode')}'")
    return errs


def check_row_L1(row):
    """L1: L0 + complete signal object with all five fields."""
    errs = []
    sig = row.get("signal")
    if not isinstance(sig, dict):
        return ["missing 'signal' object"]
    for f in SIGNAL_FIELDS:
        if not _is_nonempty_str(sig.get(f)):
            errs.append(f"signal.{f} missing/empty")
    if sig.get("masquerade_face") not in FACES:
        errs.append(f"signal.masquerade_face invalid: {sig.get('masquerade_face')}")
    if "=>" not in str(sig.get("verdict_rule", "")):
        errs.append("signal.verdict_rule not machine-checkable (no '=>')")
    return errs


def check_row_L2(row):
    """L2 record-level: fail-closed rows must have absolute windows and deny rules."""
    errs = []
    sig = row.get("signal") or {}
    if sig.get("window_status") in ABSOLUTE_WINDOW_STATUS:
        rule = str(sig.get("verdict_rule", "")).lower()
        if not any(m in rule for m in ("deny", "explicit_failure", "silent_timeout")):
            errs.append("absolute window without a deny/failure verdict rule")
    return errs


def run_tck(path):
    rows, parse_errors = [], []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                parse_errors.append(f"line {i}: invalid JSON: {e}")

    meta = next((r for r in rows if r.get("id") == "_meta" or "_meta" in r), None)
    probes = [r for r in rows if r is not meta]

    l0_fails = [(r.get("id", "?"), check_row_L0(r)) for r in probes if check_row_L0(r)]
    l1_fails = [(r.get("id", "?"), check_row_L1(r)) for r in probes if check_row_L1(r)]
    l2_fails = [(r.get("id", "?"), check_row_L2(r)) for r in probes if check_row_L2(r)]

    has_fail_closed = any(
        (r.get("signal") or {}).get("window_status") in ABSOLUTE_WINDOW_STATUS for r in probes
    )

    print(f"TCK run on: {path}")
    print(f"  records parsed: {len(probes)} probes, {len(parse_errors)} parse errors")
    print(f"  L0 (identity + verdict contract):  {len(probes) - len(l0_fails)}/{len(probes)} pass")
    print(f"  L1 (+ complete signal objects):    {len(probes) - len(l1_fails)}/{len(probes)} pass")
    print(f"  L2 (+ fail-closed absolute rules): {len(probes) - len(l2_fails)}/{len(probes)} pass, "
          f"fail-closed row present: {has_fail_closed}")

    for rid, errs in l0_fails + l1_fails + l2_fails:
        for e in errs:
            print(f"  [FAIL] {rid}: {e}")
    for pe in parse_errors:
        print(f"  [FAIL] {pe}")

    if parse_errors or l0_fails:
        level = None
    elif not has_fail_closed or l2_fails:
        level = "L1"
    else:
        level = "L2"

    n = len(probes)
    print(f"  conformance level: {level if level else 'NONE'}"
          + (f" ({n}/{n} records)" if level else ""))
    if meta:
        declared = (meta.get("_meta") or meta).get("license", "")
        if declared:
            print(f"  declared license: {declared}")
    return level


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    result = run_tck(sys.argv[1])
    sys.exit(0 if result else 1)
