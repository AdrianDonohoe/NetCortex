# The Change Impact Agent never applies a change — read-only assessment

The Change Impact Agent answers the platform's third question: triage asks *what happened*, dispatch asks *what happens next*, impact asks *what happens if we change the network*. Its obvious evidence source is the sandbox lab — dispatch already has an Executor, and "everything executes against the lab, not a live network" is platform doctrine. We chose read-only anyway: the agent assesses a proposed Change against existing evidence (episode stores, Change History, derived dependencies, the specgraph, an optional human test plan) and writes an Impact Report; it never applies a change, not even in the lab.

## Status

accepted

_Amended 2026-09-22 — the empty-store line quoted in Consequences was reworded in implementation: once a failed Change Record can grade HIGH, "no historical evidence yet" became a lie, so the report names the stores consulted and their state instead. The honesty principle is unchanged._

## Considered Options

- **Lab-backed assessment**: the agent applies the Change in the sandbox lab, recaptures, and compares against the golden baseline, so the report carries measured deltas. Rejected for v1: it doubles the project's machinery (executor, capture orchestration, baseline comparison) before the advisory path — the report, the rubric, the stores — has proven itself, and the advisory is the platform's unclaimed moment. Adding lab execution later is additive and would be its own ADR.
- **Read-only assessment (chosen)**: the agent consumes, never mutates — except its own Change History, which only the human annotation loop writes. The report is the deliverable; a human decides and applies.

## Consequences

- **Pre-checks are pointers, not runs.** The report recommends which of the human's test-plan items matter for this change and which KPIs to watch; it never executes a check. The human owns the measurement.
- **The predicted-vs-cited discipline is load-bearing.** With no lab, every claim in the report must be marked as a prediction or a citation (an Episode, a Change Record, a capture, a spec reference). An unmarked claim would pass a guess off as evidence.
- **The first reports are honest about emptiness.** The Change History starts empty and grows only through the human annotation loop, so a line naming the stores consulted and what they hold — "is empty", "does not exist" — is normal, truthful output: the same empty-store honesty as dispatch's runbook library.
- **Adding the lab later is additive, not a rewrite.** The report schema, the rubric, and the stores don't change if a lab-backed executor arrives; a measured-delta section joins the report and the read-only boundary moves to "never outside the lab" — which is exactly dispatch's existing stance.
