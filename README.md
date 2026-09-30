# Silent Timeout Protocol

**Three states × five lifecycle buckets — an executable observation protocol for agent silent failures.**

Born in the public thread [langchain-ai/langgraph#9006](https://github.com/langchain-ai/langgraph/issues/9006), where it was first proposed, pressure-tested against the [AgentEtna/how-agents-fail](https://huggingface.co/datasets/AgentEtna/how-agents-fail) dataset rows, and independently reproduced by third parties. This repo is its permanent, citable home.

## Why

Agents fail in three ways. Two of them speak. The dangerous one doesn't.

A silent timeout — a run that stalls, half-applies side effects, or presents derived data as fresh — **masquerades as a milder state** in every stage of an agent's lifecycle. It looks like "idle", "done", "measured", or "pass". Existing failure taxonomies record *what happened*. The most dangerous part of an agent failure is **what didn't happen** — and that is exactly what no taxonomy row captures.

## The protocol

### 1. Three states — the only legal endings

| State | Contract |
|---|---|
| `SUCCESS` | Must carry artifact evidence (path or non-empty payload). A claimed success without an artifact **is** a failure. |
| `EXPLICIT_FAILURE` | Must carry a named reason. A failure without a reason is a second silence. |
| `SILENT_TIMEOUT` | No first signal within its window. Surfaced by a guard layer as a failure — equivalent, fatal. |

**There is no fourth state.** `return None`, an empty `except`, or finishing without a report all count as failure.

### 2. Five buckets — the lifecycle cross-cut

The three states unfold across five lifecycle buckets. The dangerous column is the third:

| Bucket | SUCCESS | EXPLICIT_FAILURE | SILENT_TIMEOUT (the dangerous one) |
|---|---|---|---|
| **boot** | First model/event emitted | Named init error (missing key, bad env) | Harness never emits a first event — "no scheduled run" looks identical to "agent did nothing" |
| **tools** | Artifact + side effect both recorded | Tool error surfaces explicitly | Half-applied side effects with no error — resume must reconcile the ledger first |
| **memory** | Write/read with digest | Named corruption error | Derived data masquerading as fresh measurement |
| **loop** | Converges, emits artifact | Budget/step cap hit, with a record | Stall with no terminal state — resume decided by the ledger, not the checkpoint |
| **guardrails** | Policy check passed, pass record persisted | `POLICY_DENIED` with reason, fail-closed | **The check itself is missing — must be treated as denial, never as pass** |

### 3. First Signal — turn names into checkable predicates

Each bucket defines the first observable event that counts as "alive". `SILENT_TIMEOUT` stops being a label and becomes a **detectable predicate**:

```
SILENT_TIMEOUT(bucket) := deadline ∧ ¬first_signal(bucket)
```

| Bucket | First Signal (presence = alive) | SILENT_TIMEOUT formalized |
|---|---|---|
| boot | first model/event emitted | `deadline ∧ ¬first_event` |
| tools | artifact + side-effect record | `deadline ∧ ¬side_effect_record` |
| memory | write/read with digest | `deadline ∧ ¬write_digest` |
| loop | step counter advanced | `deadline ∧ ¬step_advance` |
| guardrails | policy-check record persisted | `deadline ∧ ¬policy_record` |

### 4. Discriminating probes — catch the masquerade

| Bucket | Masquerades as | Probe that catches it |
|---|---|---|
| boot | no-run → idle | Forced heartbeat: alarm if no first event within N seconds — don't wait for polling |
| tools | half-applied → done | Side-effect ledger reconciliation before resume; unbalanced → roll back |
| memory | derived → measured | Freshness boundary: a read must carry its source's measurement timestamp, not derivation time |
| loop | stall → converging | Step coverage: k consecutive iterations with no artifact delta = stall, regardless of "still running" |
| guardrails | absent-check → pass | **Absence is denial**: no policy-check record on file = `POLICY_DENIED`, fail closed |

### 5. Negative observation ledger — record what didn't happen

A proposed extension for failure datasets: alongside each row's `observed`, an optional `missing_signals` field:

```yaml
failure_id: stm-tools-001
bucket: tools
verdict: silent_timeout
observed: "resume proceeded from checkpoint"
missing_signals:          # the core increment: negative observation
  - side_effect_record
probe_fired: ledger_reconcile
masqueraded_as: "clean resume"
```

> Existing taxonomies enumerate what happened. This field records what didn't — and the most dangerous part of an agent failure is the part that didn't happen.

## Quick start

Stdlib-only Python, no dependencies:

```bash
python python/silent_timeout_probe.py                                  # self-test (8/8)
python tck/conformance_runner.py probes/silent-family-candidates.jsonl # conformance check
```

```python
from silent_timeout_probe import probe

verdict, evidence = probe(
    first_signal_fn=lambda: None,   # your signal callback
    deadline_s=2.0,
)
# ('SILENT_TIMEOUT', None) — silence, surfaced as a first-class failure
```

## Specification & conformance

- **[SPEC v0.1](spec/SPEC.md)** — the normative spec: terms, three-state verdict contract, five-bucket First Signal predicates, fail-closed absolute rules, versioning & governance.
- **[signal.schema.json](schema/signal.schema.json)** — machine-readable schema for the `signal.*` protocol extension.
- **[TCK](tck/conformance_runner.py)** — the conformance test kit. Run it over your JSONL records:

| Level | Means |
|---|---|
| **L0** | Three-state verdict contract on identity + expected fields |
| **L1** | Complete `signal.*` objects (first_signal / window / window_status / masquerade_face / verdict_rule) |
| **L2** | Fail-closed absolute rules present, machine-checkable verdict rules |

The bundled candidate probes conform at **L2 (6/6 records)**. An adopter MAY advertise: *"silent-timeout-protocol L2 conformant (TCK v0.1, N/N records)"*.

## Adopters

*Status: candidate adopters — this list is honest, not aspirational.*

- [AgentEtna/how-agents-fail](https://huggingface.co/datasets/AgentEtna/how-agents-fail) — silent-family candidate rows under line-by-line adjudication (fold proposed per the agreed async process in #9006)
- [shimjaemandu/reality-layer](https://github.com/shimjaemandu/reality-layer) — independent external runtime checkpoint built against the three-state framing from the same thread

Own an agent harness? Run the TCK and open a PR to list your conformance level here.

## Candidate probe rows

[`probes/silent-family-candidates.jsonl`](probes/silent-family-candidates.jsonl) — the silent-family candidate file delivered to the how-agents-fail adjudication process (6 probe rows + `_meta`, all five buckets, all four masquerade faces). Status and provenance are declared in its `_meta` row.

## Honest boundary

These are **protocol-layer candidates**. Thresholds are calibration points, not universals; none of the probe rows has been run against live traces yet. Treat everything here as *an argument to adapt, not a claim to match* your deployment.

## Provenance & attribution (CC-BY-4.0)

- First public proposal and v0.1/v0.2 protocol development: [@chenhz01](https://github.com/chenhz01) in [langchain-ai/langgraph#9006](https://github.com/langchain-ai/langgraph/issues/9006)
- Dataset context and cross-verification: [AgentEtna/how-agents-fail](https://huggingface.co/datasets/AgentEtna/how-agents-fail) (CC-BY-4.0) — thank you for the open rows and the open adjudication process
- Independent reproduction of the three-state framing by thread participants is the best signal this protocol generalizes

## OpenCore

The spec, the TCK, the probe code, and the candidate rows are free forever (CC-BY-4.0). If you want the applied version — silent-failure auditing and output health checks for your own agent pipelines, with a conformance report — contact [@chenhz01](https://github.com/chenhz01).

## License

CC-BY-4.0. Attribution to the langgraph#9006 thread appreciated but not required for the protocol itself.
