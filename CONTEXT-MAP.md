# Context Map

**NetCortex** is the platform — an agentic AI platform for autonomous
network operations. The three current contexts:

## Contexts

- [5gcap](./CONTEXT.md) — deterministic, offline decoding of NGAP/NAS, PFCP, and SBI (HTTP/2) captures into Flows, Procedures, and KPIs. No network access, no LLM dependency, fully reproducible run-to-run.
- [triage](./triage/CONTEXT.md) — LLM-agent root-cause hypothesis generation for failed Registration/PDU-session Procedures, SBI service transactions, and N4 (PFCP) session-management procedures. Non-deterministic, depends on an LLM, a 3GPP-spec RAG index, and an episodic memory store.
- [dispatch](./dispatch/CONTEXT.md) — event-driven incident orchestration: Alarm events fan out to PCAP/Log/KPI specialist agents, deterministic evidence correlation, root-cause investigation, remediation proposals gated on human approval. Sandbox-scoped, per-invocation (not a live monitor).
- [impact](./impact/CONTEXT.md) — pre-change advisory: assesses a proposed Change (NF upgrade, config change) against the platform's existing evidence and writes an Impact Report — a cited risk grade, affected NFs, historical evidence, recommended pre-checks, rollback criteria. Read-only by design; a human decides and applies.

Shared, cross-cutting infrastructure not owned by either context:

- [`sandbox/`](./sandbox/) — Open5GS + UERANSIM lab. Generates real captures for 5gcap's own fixtures, and (once extended) failure-injection scenarios with labeled ground truth for triage's evals.

## Relationships

- **triage → 5gcap**: triage consumes 5gcap's decode output (Flows, Procedures, decoded messages/IEs) as its evidentiary substrate; it does not re-implement or bypass decoding.
- **triage → sandbox**: triage's eval harness consumes sandbox failure-injection fixtures and their labeled ground-truth `incident_type` to score `type_accuracy` and `diagnosis_quality`.
- **5gcap → sandbox**: 5gcap's test suite consumes sandbox-generated captures (`sandbox_n2.pcap`, `sandbox_n4.pcap`) as fixtures, alongside its third-party-sourced ones.
- **dispatch → 5gcap**: dispatch consumes 5gcap's decode and KPIs by subprocess (the JSON contract) — decode never runs inside the Dispatcher's process; `detect-kpi` compares 5gcap's computed KPIs against the golden baseline.
- **dispatch → triage**: the PCAP Agent runs `triage analyze` per event; the root-cause investigation imports triage's LATS machinery (Tree, signatures) as a library — dispatch is the only context that depends on triage's Python API.
- **dispatch → sandbox**: every executable action is sandbox-scoped (restart NF, revert config, re-seed subscriber, re-run capture); events, logs, and remediation targets live in the Open5GS+UERANSIM lab.
- **impact → 5gcap**: impact consumes 5gcap's decode/correlation output from prior captures to derive a Change's blast radius (NFs, Procedures, KPIs); decode never runs inside impact's process.
- **impact → triage / dispatch**: impact is a pure consumer of both episode stores (`triage/memory/episodes.jsonl`, dispatch's `episodes.jsonl`) and triage's post-incident reports — historical evidence for the rubric. It builds no index of its own.
- **impact → sandbox**: none — impact never applies anything, even in the lab. The read-only boundary is [`impact/docs/adr/0001`](./impact/docs/adr/0001-read-only-change-assessment.md).
