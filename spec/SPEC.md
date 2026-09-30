# Silent Timeout Protocol — Specification v0.1

**Status:** Emerging specification. Stable for adopters; expect additive changes only until v1.0.
**Born in:** [langchain-ai/langgraph#9006](https://github.com/langchain-ai/langgraph/issues/9006)
**License:** CC-BY-4.0
**Reference implementation:** [`python/silent_timeout_probe.py`](../python/silent_timeout_probe.py) (stdlib-only)
**Conformance suite:** [`tck/conformance_runner.py`](../tck/conformance_runner.py)
**Machine-readable schema:** [`schema/signal.schema.json`](../schema/signal.schema.json)

---

## 1. Terms

| Term | Definition |
|---|---|
| **Agent run** | One execution attempt of an agent task, from dispatch to terminal state. |
| **Bucket** | One of five lifecycle stages: `boot`, `tools`, `memory`, `loop`, `guardrails`. |
| **First Signal** | The earliest observable event within a bucket that counts as evidence of being alive. |
| **Window** | A bounded duration within which the First Signal must appear. |
| **Verdict** | The single mandatory outcome classification of a stage or run. |
| **Masquerade face** | The milder state a silent failure pretends to be: `idle`, `done`, `measured`, `pass`. |
| **Negative observation** | A recorded fact about what *did not* happen (`missing_signals`). |

## 2. Verdict contract (the three states)

Every stage and every run MUST end in exactly one of:

| Verdict | MUST carry | A verdict without this is... |
|---|---|---|
| `SUCCESS` | artifact evidence (path or non-empty payload) | a violation → classify as `EXPLICIT_FAILURE` |
| `EXPLICIT_FAILURE` | a named reason | a violation ("second silence") → classify as `EXPLICIT_FAILURE` |
| `SILENT_TIMEOUT` | (surfaced by a guard) no First Signal within the Window | — |

**There is no fourth state.** `return None`, an empty `except`, an empty-string success, and terminating without a report MUST all be classified as `EXPLICIT_FAILURE`. Absence of evidence MUST NOT be classified as skipped, idle, or success.

## 3. Buckets and First Signal predicates

| Bucket | First Signal (presence = alive) | SILENT_TIMEOUT predicate |
|---|---|---|
| `boot` | first model/event emitted (including error events) | `deadline ∧ ¬first_event` |
| `tools` | artifact evidence AND side-effect ledger entry, together | `deadline ∧ ¬side_effect_record` |
| `memory` | read keyed to source measurement timestamp with intact freshness boundary | `deadline ∧ ¬write_digest` |
| `loop` | per-iteration convergence delta OR terminal state OR budget-exhaustion record | `deadline ∧ ¬step_advance` |
| `guardrails` | policy-check pass record persisted **before** execution | `deadline ∧ ¬policy_record` |

## 4. Fail-closed rules (absolute, not calibration)

1. **Absent check is denial.** A guardrail action with no persisted pass record at execution time MUST be `DENIED` (`POLICY_DENIED`, reason: "check record missing"). Malformed records are also denials.
2. **Freshness boundary.** A derived record whose timestamp exceeds its source measurement timestamp MUST be `EXPLICIT_FAILURE` (stale-as-fresh).
3. **Resume requires reconciliation.** Resuming from a checkpoint MUST NOT proceed before side-effect ledger reconciliation; an artifact without a ledger entry is `EXPLICIT_FAILURE`.

Windows other than the above are **calibration points**: adopters re-base them per deployment. The three rules above MUST NOT be calibrated away.

## 5. The `signal.*` object

Probe rows SHOULD carry a `signal` object conforming to [`schema/signal.schema.json`](../schema/signal.schema.json):

| Field | Type | Constraint |
|---|---|---|
| `first_signal` | string | concrete, observable, includes error events |
| `window` | string | bounded; describes the calibration basis |
| `window_status` | enum | `calibration point` or `absolute, not a calibration point` |
| `masquerade_face` | enum | `idle` \| `done` \| `measured` \| `pass` |
| `verdict_rule` | string | MUST contain machine-checkable `=>` rules |

## 6. Negative observation ledger (L2 extension)

Failure records SHOULD optionally carry:

```yaml
missing_signals:        # what did not happen
  - side_effect_record
probe_fired: ledger_reconcile
masqueraded_as: "clean resume"
```

> Existing taxonomies enumerate what happened. The `missing_signals` field records what didn't — the most dangerous part of an agent failure is the part that didn't happen.

## 7. Conformance levels

A harness or dataset claims conformance by running [`tck/conformance_runner.py`](../tck/conformance_runner.py) over its JSONL records:

| Level | Requirements |
|---|---|
| **L0** | Records carry `id`, `category` (valid bucket), `failure_mode`, and a non-empty `expected` with a three-state verdict contract. |
| **L1** | L0 **plus** every record carries a `signal` object with all five fields (§5). |
| **L2** | L1 **plus** at least one fail-closed record with an absolute (non-calibratable) window, and every record's `verdict_rule` is machine-checkable (`=>` syntax). |

An adopter MAY advertise: *"silent-timeout-protocol L2 conformant (TCK vX.Y, N/N records)"*.

## 8. Versioning and governance

- This spec follows semver: additive fields = minor; breaking changes = major.
- Changes via pull request to this repository; the #9006 thread is the provenance of record.
- Stability promise: v0.x adopters are guaranteed a mechanical re-mapping path (never a semantic rewrite) to v1.0.

## 9. Honest boundary

Protocol-layer candidates: thresholds are calibration points, not universals. Live-trace validation status is tracked per row in the probe `_meta`. Everything here is *an argument to adapt, not a claim to match* any specific deployment.
