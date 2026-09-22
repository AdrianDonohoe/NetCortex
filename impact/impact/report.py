"""The Impact Report: the agent's sole deliverable.

Every claim line carries exactly one marker — [cited] with a source, or
[predicted] — and the renderer refuses to emit a bare claim: the
assembled report is validated before it leaves. With no lab,
prediction must never read as measurement. Section headings are
structure, not claims, and are exempt from marking.
"""

from __future__ import annotations

from dataclasses import dataclass

from .change import Change, ChangeType
from .evidence import (
    Evidence,
    dispatch_episode_mentions,
    report_mentions,
    triage_episode_mentions,
)
from .rubric import RiskGrade, Rubric


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
    no_procedures = Claim(
        "No Procedures or KPIs determinable — no capture evidence consulted.",
        source="no captures consulted",
    ).render()
    no_prechecks = Claim(
        "None — no test plan provided.", source="no test plan input"
    ).render()
    no_rollback = Claim(
        "None — no KPI watch points determinable without capture evidence.",
        source="no captures consulted",
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
    lines.extend(
        [
            "",
            "## Affected Network Functions",
            "",
            f"- {target_line}",
            f"- {no_procedures}",
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
            f"- {no_rollback}",
            "",
        ]
    )
    _validate_markers(lines)
    return "\n".join(lines)
