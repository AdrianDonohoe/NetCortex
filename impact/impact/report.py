"""The Impact Report: the agent's sole deliverable.

Every claim line carries exactly one marker — [cited] with a source, or
[predicted] — and the renderer refuses to emit a bare claim: the
assembled report is validated before it leaves. With no lab,
prediction must never read as measurement. Section headings are
structure, not claims, and are exempt from marking.
"""

from __future__ import annotations

from dataclasses import dataclass

from .capture import blast_radius
from .change import Change, ChangeType
from .evidence import (
    Evidence,
    capture_note,
    dispatch_episode_mentions,
    report_mentions,
    triage_episode_mentions,
)
from .rubric import RiskGrade, Rubric
from .specgraph import reference_partners, sbi_entities, service_family


class UnmarkedClaimError(ValueError):
    """A claim with neither a citation nor a predicted marker."""


@dataclass(frozen=True)
class Claim:
    text: str
    predicted: bool = False
    source: str | None = None

    def render(self) -> str:
        if self.predicted:
            if self.source is not None:
                raise UnmarkedClaimError(
                    f"predicted claim carries a citation: {self.text!r}"
                )
            return f"{self.text} [predicted]"
        if self.source is None:
            raise UnmarkedClaimError(f"bare claim: {self.text!r}")
        return f"{self.text} [cited: {self.source}]"


def _validate_markers(lines: list[str]) -> None:
    """Backstop: no non-heading, non-empty line leaves without exactly one marker."""
    for line in lines:
        if not line.strip() or line.startswith("#"):
            continue
        markers = line.count("[cited: ") + line.count("[predicted]")
        if markers != 1:
            raise UnmarkedClaimError(f"marker discipline broken on: {line!r}")


def _reference_lines(change: Change, evidence: Evidence) -> list[str]:
    """Affected NFs from specgraph references when no capture locates the target.

    Lists the target family's service operations and its reference
    dependencies; a missing store is named, never asserted clear.
    """
    partners = reference_partners(evidence.specgraph, change.target)
    if partners:
        note = capture_note(evidence.capture, change.target)
        lines = [
            f"- {Claim(f'{note}; specgraph reference points', source=str(evidence.specgraph.path)).render()}"
        ]
        for entity in sbi_entities(
            evidence.specgraph, service_family(change.target)
        ):
            name = entity.get("name")
            lines.append(
                f"  - {Claim(f'Service operation {name}', source=f'{evidence.specgraph.path}:{entity.get('id')}').render()}"
            )
        lines.extend(
            f"- {Claim(f'{partner.role} — reference dependency', source=f'{evidence.specgraph.path}:{','.join(partner.evidence)}').render()}"
            for partner in partners
        )
        return lines
    consulted = [
        str(state.path)
        for state in (evidence.capture, evidence.specgraph)
        if state.consulted
    ]
    missing = [
        state.describe()
        for state in (evidence.capture, evidence.specgraph)
        if state.path is not None and not state.exists
    ]
    if consulted:
        line = (
            f"No Procedures or KPIs determinable — {change.target} has no "
            f"determinable partners in {', '.join(consulted)}"
        )
        if missing:
            line += "; " + "; ".join(missing)
        return [f"- {Claim(line, source=', '.join(consulted)).render()}"]
    if missing:
        line = "No Procedures or KPIs determinable; " + "; ".join(missing)
        source = ", ".join(
            str(state.path)
            for state in (evidence.capture, evidence.specgraph)
            if state.path is not None
        )
        return [f"- {Claim(line, source=source).render()}"]
    return [
        f"- {Claim('No Procedures or KPIs determinable — no capture or specgraph evidence consulted', source='no capture or specgraph evidence consulted').render()}"
    ]


def render_report(change: Change, rubric: Rubric, evidence: Evidence) -> str:
    """Render the Impact Report; every claim goes through Claim.render."""
    lines: list[str] = [
        "# Impact Report",
        "",
        Claim(f"**Change:** {change.describe()}", source="change record").render(),
        "",
        f"## CHANGE RISK: {rubric.grade.value}",
        "",
    ]
    for factor in rubric.factors:
        lines.append(
            f"- {Claim(f'{factor.name}: {factor.finding}', source=factor.citation).render()}"
        )
    if rubric.grade is RiskGrade.INSUFFICIENT_EVIDENCE:
        lines.append(
            Claim(
                "The rubric cannot be applied on empty evidence; an "
                "unknowable risk is never graded LOW.",
                source="the rubric's doctrine (ADR-0001)",
            ).render()
        )
    result = (
        blast_radius(change, evidence.capture)
        if change.type is ChangeType.UPGRADE
        else None
    )
    if change.type is ChangeType.UPGRADE:
        target_line = Claim(
            f"{change.target} — the Change's own target",
            source="change record",
        ).render()
    else:
        target_line = Claim(
            "No NFs determinable — the Change names a config key, "
            "not a network function",
            source="change record",
        ).render()
    no_prechecks = Claim(
        "None — no test plan provided.", source="no test plan input"
    ).render()
    if result is not None and result.target is not None:
        rollback = Claim(
            "Any regression in the capture-derived Procedures and KPIs "
            "above during the Change",
            source=str(evidence.capture.path),
        ).render()
    else:
        consulted = [
            str(state.path)
            for state in (evidence.capture, evidence.specgraph)
            if state.consulted
        ]
        rollback = Claim(
            "None — no KPI watch points derivable from the evidence consulted.",
            source=", ".join(consulted) or "no capture or specgraph evidence consulted",
        ).render()
    history_bullets = [
        f"- {Claim(f'Change History: {evidence.history.describe()}', source='the evidence stores').render()}",
        f"- {Claim(f'Triage Episodes: {evidence.triage_episodes.describe()}', source='the evidence stores').render()}",
        f"- {Claim(f'Dispatch Episodes: {evidence.dispatch_episodes.describe()}', source='the evidence stores').render()}",
        f"- {Claim(f'Post-incident reports: {evidence.reports.describe()}', source='the evidence stores').render()}",
    ]
    for mention in triage_episode_mentions(
        evidence.triage_episodes, change.target
    ) + dispatch_episode_mentions(evidence.dispatch_episodes, change.target):
        history_bullets.append(
            f"- {Claim(f'Episode {mention.label}: {mention.narrative}', source=mention.citation).render()}"
        )
    for path, mention_lines in report_mentions(evidence.reports, change.target):
        history_bullets.append(
            f"- {Claim(f'Post-incident report {path} mentions {change.target}', source=f'{path}:{','.join(map(str, mention_lines))}').render()}"
        )
    affected_lines = [f"- {target_line}"]
    if result is not None and result.target is not None:
        for nf in result.affected:
            affected_lines.append(
                f"- {Claim(nf.role, source=f'{evidence.capture.pointer_source(nf.evidence)}:{nf.evidence}').render()}"
            )
            for procedure in nf.procedures:
                outcome = (
                    f", outcome {procedure.outcome}" if procedure.outcome else ""
                )
                affected_lines.append(
                    f"  - {Claim(f'Procedure {procedure.kind}{outcome}', source=f'{evidence.capture.pointer_source(procedure.pointer)}:{procedure.pointer}').render()}"
                )
            if nf.procedures:
                pointers = ", ".join(
                    f"{evidence.capture.pointer_source(procedure.pointer)}:{procedure.pointer}"
                    for procedure in nf.procedures
                )
                kpis = nf.kpis
                affected_lines.append(
                    f"  - {Claim(f'KPI procedures={kpis.count}, accept={kpis.successes}, reject={kpis.failures}', source=pointers).render()}"
                )
            else:
                affected_lines.append(
                    f"  - {Claim('no Procedures or KPIs derivable', source=f'{evidence.capture.pointer_source(nf.evidence)}:{nf.evidence}').render()}"
                )
        if result.unknown_peers:
            pointers = ", ".join(
                f"{evidence.capture.pointer_source(pointer)}:{pointer}"
                for pointer in result.unknown_peer_pointers
            )
            affected_lines.append(
                f"- {Claim(f'{result.unknown_peers} peer(s) with no determinable role', source=pointers).render()}"
            )
        if not result.affected and not result.unknown_peers:
            affected_lines.append(
                f"- {Claim(f'{change.target} exchanges no messages with any other NF in the capture', source=f'{evidence.capture.pointer_source(result.target.evidence)}:{result.target.evidence}').render()}"
            )
    elif change.type is ChangeType.UPGRADE:
        affected_lines.extend(_reference_lines(change, evidence))
    lines.extend(
        [
            "",
            "## Affected Network Functions",
            "",
            *affected_lines,
            "",
            "## Historical Evidence",
            "",
            *history_bullets,
            "",
            "## Recommended Pre-Checks",
            "",
            f"- {no_prechecks}",
            "",
            "## Rollback Criteria",
            "",
            f"- {rollback}",
            "",
        ]
    )
    _validate_markers(lines)
    return "\n".join(lines)
