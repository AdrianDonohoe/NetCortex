# impact

Pre-change advisory for the NetCortex stack: a proposed Change — an NF
software upgrade or a config change — is assessed by a single agent
against the platform's existing evidence before it is applied. The
agent reads the episode stores, the Change History, prior captures'
dependency structure, the 3GPP specgraph, and an optional human test
plan, then writes an Impact Report: a risk grade with cited factors,
affected network functions, historical evidence, recommended
pre-checks, and rollback criteria. Read-only by design: the agent
never applies a change, not even in the sandbox lab — the report is
the deliverable, and a human decides and applies. The read-only
boundary:
[`docs/adr/0001-read-only-change-assessment.md`](./docs/adr/0001-read-only-change-assessment.md).

## Language

**Change**:
A proposed network modification, expressed as a structured record with
a deliberately small vocabulary of two: `upgrade <nf> <old>→<new>` and
`config <key> <old>→<new>`. Config differences enter as structured
fields of the record, never as raw diffs. The vocabulary grows the way
dispatch's runbook library does — as fast as real uses promote it.
_Avoid_: patch, request, ticket

**Change Record**:
The stored form of a Change: the Impact Report annotated with the
human's outcome (applied / rejected / rolled-back) after the fact.
Written only by the human loop — the agent never writes its own
history.
_Avoid_: change log entry, history item

**Outcome**:
The human's after-the-fact word on a Change: applied, rejected, or
rolled-back. Rejected and rolled-back are failed outcomes — a new
Change matching a past failed record (same target, same class)
grades HIGH through the historical-evidence factor.
_Avoid_: result, status

**Change History**:
The store of Change Records (`impact/memory/changes.jsonl`). Starts
empty and grows only through the human annotation loop — dispatch's
Learning-loop pattern, so the first reports honestly say "no
historical evidence yet".
_Avoid_: changelog, audit trail

**Impact Report**:
The agent's sole deliverable: a Risk grade with its cited factors,
affected NFs (for the human) with the Procedures and KPIs beneath them
(for the evidence), historical evidence, recommended pre-checks, and
rollback criteria. Every claim is marked cited vs predicted — with no
lab, prediction must never read as measurement.
_Avoid_: assessment, analysis, finding

**Blast radius**:
The set of NFs, Procedures, and KPIs a Change touches. Derived from
prior captures via the platform's own decode/correlation, falling back
to specgraph reference points when no capture covers the network.
Never hand-maintained: a dependency store that drifts from the wire is
not evidence.
_Avoid_: impact scope, affected area

**Critical interface**:
SBI to UDM or AUSF (`Nudm_*`/`Nausf_*`) or the N2 control plane's SBI
face (`Namf_Communication_N1N2MessageTransfer`). One inside the Blast
radius makes the dependency criticality factor critical and grades the
Change HIGH. The factor never asserts the absence of one without full
knowledge of the radius.
_Avoid_: sensitive interface, core dependency

**Pre-checks**:
The report's Recommended Pre-Checks section: the human's test-plan
items inside the Blast radius plus KPI watch points. The agent selects
and prioritizes them for the change at hand; it never runs a check.
_Avoid_: verification steps, test run

**Test plan**:
The human's structured list of checks for a proposed Change, supplied
alongside the Change Record: named items, each optionally pinned to an
NF. Read and prioritized only — nothing in the pipeline executes a
check, so thresholds render verbatim and are never evaluated.
_Avoid_: test run, verification suite

**Plan item**:
One entry of the Test plan: a name and an optional NF pin. An item
whose NF is the Change's target sits closest; one naming a partner sits
next; the rest are outside the Blast radius and are reported as an
excluded count, never dropped silently.
_Avoid_: check, test case

**Watch point**:
A Plan item carrying a KPI and a threshold. Rendered in both Pre-checks
and Rollback criteria — the threshold is the human's, verbatim, and the
agent never evaluates it.
_Avoid_: alert, monitor

**Proximity**:
How close a Plan item's NF is to the Change's target: the target itself
(distance 0) before its partners (distance 1), plan order preserved
within each group.
_Avoid_: relevance, priority

**Risk grade**:
One of HIGH / MEDIUM / LOW / INSUFFICIENT EVIDENCE, computed by a
fixed rubric in code from three factors — historical evidence,
dependency criticality, blast radius — each factor cited to its source
in the report. An unknowable risk never prints as LOW.
_Avoid_: severity, confidence, score
