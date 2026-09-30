"""silent_timeout_probe.py — minimal three-state verifier for agent silent failures.

Protocol: three states x five lifecycle buckets.
Born in langchain-ai/langgraph#9006. CC-BY-4.0.

Contract:
    SUCCESS           -> must carry artifact evidence
    EXPLICIT_FAILURE  -> must carry a named reason
    SILENT_TIMEOUT    -> no first signal within window (surfaced by the guard)

There is no fourth state: None / empty return / missing record = failure.
"""

import time

SUCCESS = "SUCCESS"
EXPLICIT_FAILURE = "EXPLICIT_FAILURE"
SILENT_TIMEOUT = "SILENT_TIMEOUT"


def probe(first_signal_fn, deadline_s, poll_s=0.05):
    """Run first_signal_fn() until it reports or the deadline passes.

    first_signal_fn returns:
        None                      -> nothing observed yet (keep polling)
        ("reason", ...)           -> explicit failure, carries a named reason
        any other truthy value    -> SUCCESS, value is the artifact evidence

    Returns (verdict, evidence_or_reason_or_None).
    """
    start = time.monotonic()
    while time.monotonic() - start < deadline_s:
        signal = first_signal_fn()
        if signal is None:
            time.sleep(poll_s)
            continue
        # A bare empty string / empty container is not a signal: a "successful"
        # return carrying no artifact and no reason is EXPLICIT_FAILURE.
        if not signal or signal == "":
            return (EXPLICIT_FAILURE, "empty signal returned without a reason")
        if isinstance(signal, tuple) and signal and isinstance(signal[0], str):
            if signal[0] in (SUCCESS, EXPLICIT_FAILURE, SILENT_TIMEOUT):
                if signal[0] == EXPLICIT_FAILURE:
                    return (EXPLICIT_FAILURE, signal[1] or "unnamed failure")
                if signal[0] == SUCCESS:
                    return (SUCCESS, signal[1])
                return (SILENT_TIMEOUT, signal[1])
            return (EXPLICIT_FAILURE, signal[0])  # named reason tuple
        return (SUCCESS, signal)
    return (SILENT_TIMEOUT, None)


def guardrail_absent_is_denial(policy_record):
    """Fail-closed rule: an absent policy check record is a denial, never a pass."""
    if not policy_record:
        return "DENIED"
    return "ALLOWED" if policy_record.get("pass") is True else "DENIED"


def _self_test():
    results = []

    # 1. success carries artifact evidence
    v, e = probe(lambda: "artifact/report.md", deadline_s=1.0)
    results.append(("success carries artifact", v == SUCCESS and e == "artifact/report.md"))

    # 2. explicit failure carries a named reason
    v, e = probe(lambda: (EXPLICIT_FAILURE, "missing API key"), deadline_s=1.0)
    results.append(("explicit failure carries reason", v == EXPLICIT_FAILURE and e == "missing API key"))

    # 3. silence within deadline is surfaced as SILENT_TIMEOUT
    v, e = probe(lambda: None, deadline_s=0.2)
    results.append(("silence surfaced as failure", v == SILENT_TIMEOUT))

    # 4. fake success (None / empty) is caught, not accepted
    v, e = probe(lambda: "", deadline_s=1.0)
    results.append(("empty success caught", v == EXPLICIT_FAILURE and "empty" in str(e)))

    # 5. unnamed failure is a second silence -> still explicit, reason auto-named
    v, e = probe(lambda: (EXPLICIT_FAILURE, None), deadline_s=1.0)
    results.append(("unnamed failure auto-named", v == EXPLICIT_FAILURE and e == "unnamed failure"))

    # 6. guardrails: absent check record = DENIED (fail-closed), the hardest rule
    results.append(("absent check = denial", guardrail_absent_is_denial(None) == "DENIED"))
    results.append(("malformed check = denial", guardrail_absent_is_denial({}) == "DENIED"))
    results.append(("pass record = allowed", guardrail_absent_is_denial({"pass": True}) == "ALLOWED"))

    ok = sum(1 for _, passed in results if passed)
    for name, passed in results:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    print(f"self-test: {ok}/{len(results)} passing")
    return ok == len(results)


if __name__ == "__main__":
    import sys
    sys.exit(0 if _self_test() else 1)
