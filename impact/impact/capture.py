"""The capture-derived blast radius: roles, partners, per-NF evidence.

impact consumes 5gcap's decode/correlation output from prior captures —
decode never runs inside impact's process (CONTEXT-MAP). Role inference
reimplements triage's rules because the two contexts cannot share code:
gNB/AMF from the first InitialUEMessage, SMF/UPF from the PFCP CP→UP
messages, SBI producers from service-name families. Every claim carries
a JSON pointer into the capture document so the report can cite it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .change import Change

_SBI_FAMILY = re.compile(r"^N[a-z]{2,}$")


@dataclass(frozen=True)
class Role:
    """One network function as the wire proves it: role, IP, evidence."""

    role: str
    ip: str
    evidence: str  # JSON pointer within the capture document


@dataclass(frozen=True)
class ProcedureHit:
    """One procedure attributed to an affected NF, with its pointer."""

    pointer: str
    kind: str
    outcome: str


@dataclass(frozen=True)
class KpiStats:
    """Derived per-NF stats over attributed procedures, in code."""

    count: int
    successes: int
    failures: int


@dataclass(frozen=True)
class AffectedNF:
    """One NF the Change touches beyond itself, with its evidence."""

    role: str
    ip: str
    evidence: str
    procedures: tuple[ProcedureHit, ...] = ()
    kpis: KpiStats = field(default_factory=lambda: KpiStats(0, 0, 0))


@dataclass(frozen=True)
class BlastResult:
    """The blast radius: the target as located, its partners, unknowns."""

    target: Role | None
    affected: tuple[AffectedNF, ...]
    unknown_peers: int  # peers with no determinable role
    unknown_peer_pointers: tuple[str, ...] = ()  # the messages that revealed them


@dataclass(frozen=True)
class CaptureState:
    """What a decoded capture holds: path, sections, existence.

    The merged export embeds n4 and sbi under the n2 document; separate
    exports arrive as their own sections with their own paths, so a
    pointer into a separate export cites that export's file, not the n2
    document. A missing capture must never read as an observed empty
    capture, so absence is its own state.
    """

    path: str | None
    n2: dict | None = None
    n4: dict | None = None
    sbi: dict | None = None
    exists: bool = True
    n4_path: str | None = None
    sbi_path: str | None = None

    @property
    def consulted(self) -> bool:
        """True when the capture was read and can attest to what it holds."""
        return self.path is not None and self.exists

    def pointer_source(self, pointer: str) -> str | None:
        """The file a pointer cites into: separate exports own their sections."""
        if pointer.startswith("n4/") and self.n4_path is not None:
            return self.n4_path
        if pointer.startswith("sbi/") and self.sbi_path is not None:
            return self.sbi_path
        return self.path

    def describe(self) -> str:
        if self.path is None:
            return "not consulted"
        if not self.exists:
            return f"{self.path} does not exist"
        flows = len((self.n2 or {}).get("flows") or [])
        n4_messages = len((self.n4 or {}).get("messages") or [])
        sbi_messages = len((self.sbi or {}).get("messages") or [])
        return (
            f"{self.path} holds {flows} flow(s), {n4_messages} N4 message(s), "
            f"{sbi_messages} SBI message(s)"
        )


def _sbi_role_of(message: dict) -> str | None:
    """The producer NF of an SBI service name: Nnssf_NSSelection_Get → NSSF."""
    family = (message.get("name") or "").split("_", 1)[0]
    if not _SBI_FAMILY.match(family):
        return None
    return family[1:].upper()


def infer_roles(capture: CaptureState) -> tuple[Role, ...]:
    """The NFs the wire proves, with a pointer to the proving message.

    Unprovable roles are absent, never guessed: a capture without the
    proving message contributes no role.
    """
    roles: list[Role] = []
    seen: set[tuple[str, str]] = set()

    def add(role: str, ip: str | None, evidence: str) -> None:
        if ip and (role, ip) not in seen:
            seen.add((role, ip))
            roles.append(Role(role, ip, evidence))

    # gNB and AMF: the first InitialUEMessage names both ends.
    found = False
    for flow_index, flow in enumerate((capture.n2 or {}).get("flows") or []):
        for message_index, message in enumerate(flow.get("messages") or []):
            if message.get("name") == "InitialUEMessage":
                add(
                    "gNB",
                    message.get("src_ip"),
                    f"flows/{flow_index}/messages/{message_index}",
                )
                add(
                    "AMF",
                    message.get("dst_ip"),
                    f"flows/{flow_index}/messages/{message_index}",
                )
                found = True
                break
        if found:
            break

    # SMF and UPF: the PFCP association setup request, else the first
    # session establishment request, names both ends.
    n4_messages = (capture.n4 or {}).get("messages") or []
    chosen = next(
        (
            index
            for index, message in enumerate(n4_messages)
            if "association setup request" in (message.get("name") or "").lower()
        ),
        None,
    )
    if chosen is None:
        chosen = next(
            (
                index
                for index, message in enumerate(n4_messages)
                if "pfcp session establishment request"
                in (message.get("name") or "").lower()
            ),
            None,
        )
    if chosen is not None:
        message = n4_messages[chosen]
        add("SMF", message.get("src_ip"), f"n4/messages/{chosen}")
        add("UPF", message.get("dst_ip"), f"n4/messages/{chosen}")

    # SBI producers: the destination of a request is the family's NF.
    for index, message in enumerate(
        (capture.sbi or {}).get("messages") or []
    ):
        if message.get("direction") == "request":
            role = _sbi_role_of(message)
            if role:
                add(role, message.get("dst_ip"), f"sbi/messages/{index}")
    return tuple(roles)


def _attributed(
    nf: AffectedNF, pointer: str, procedure: dict
) -> AffectedNF:
    """The NF with one more attributed procedure and its derived KPIs."""
    outcome = procedure.get("outcome") or ""
    kpis = nf.kpis
    return AffectedNF(
        role=nf.role,
        ip=nf.ip,
        evidence=nf.evidence,
        procedures=(
            *nf.procedures,
            ProcedureHit(pointer, procedure.get("kind") or "", outcome),
        ),
        kpis=KpiStats(
            count=kpis.count + 1,
            successes=kpis.successes + (1 if outcome == "accept" else 0),
            failures=kpis.failures + (1 if outcome == "reject" else 0),
        ),
    )


def blast_radius(change: Change, capture: CaptureState) -> BlastResult:
    """The NFs a Change touches beyond itself, from the capture's wire roles.

    A partner is any other endpoint on a message the target's IP
    participates in; an endpoint without a determinable role keeps the
    count unknown — NARROW requires full knowledge. Procedures attribute
    per plane: N2 by the flow's own IPs, N4 by the SMF–UPF plane itself,
    SBI through the flow's referenced messages.
    """
    if not capture.consulted:
        return BlastResult(None, (), 0, ())
    roles = infer_roles(capture)
    role_by_ip = {role.ip: role for role in roles}
    target = next(
        (
            role
            for role in roles
            if role.role.upper() == (change.target or "").upper()
        ),
        None,
    )
    if target is None:
        return BlastResult(None, (), 0, ())

    partners: dict[str, AffectedNF] = {}
    unknown_ips: dict[str, str] = {}  # peer ip → the message that revealed it

    def note_peer(ip: str | None, pointer: str) -> None:
        if not ip or ip == target.ip:
            return
        peer = role_by_ip.get(ip)
        if peer is None:
            unknown_ips.setdefault(ip, pointer)
        elif peer.role.upper() != (change.target or "").upper():
            partners.setdefault(
                ip, AffectedNF(role=peer.role, ip=ip, evidence=peer.evidence)
            )

    for flow_index, flow in enumerate((capture.n2 or {}).get("flows") or []):
        for message_index, message in enumerate(flow.get("messages") or []):
            pointer = f"flows/{flow_index}/messages/{message_index}"
            src, dst = message.get("src_ip"), message.get("dst_ip")
            if dst == target.ip:
                note_peer(src, pointer)
            if src == target.ip:
                note_peer(dst, pointer)
    for plane_name, plane in (
        ("n4", capture.n4 or {}),
        ("sbi", capture.sbi or {}),
    ):
        for message_index, message in enumerate(plane.get("messages") or []):
            pointer = f"{plane_name}/messages/{message_index}"
            src, dst = message.get("src_ip"), message.get("dst_ip")
            if dst == target.ip:
                note_peer(src, pointer)
            if src == target.ip:
                note_peer(dst, pointer)

    # N2: a flow's procedures touch the roles whose IPs appear in the flow.
    for flow_index, flow in enumerate((capture.n2 or {}).get("flows") or []):
        flow_ips = {
            ip
            for message in flow.get("messages") or []
            for ip in (message.get("src_ip"), message.get("dst_ip"))
            if ip
        }
        for procedure_index, procedure in enumerate(
            flow.get("procedures") or []
        ):
            for partner_ip in list(partners):
                if partner_ip in flow_ips:
                    partners[partner_ip] = _attributed(
                        partners[partner_ip],
                        f"flows/{flow_index}/procedures/{procedure_index}",
                        procedure,
                    )

    # N4: procedures traverse the SMF–UPF plane itself.
    for procedure_index, procedure in enumerate(
        (capture.n4 or {}).get("procedures") or []
    ):
        for partner_ip, nf in list(partners.items()):
            if nf.role in ("SMF", "UPF"):
                partners[partner_ip] = _attributed(
                    nf, f"n4/procedures/{procedure_index}", procedure
                )

    # SBI: a procedure attributes through its flow's referenced messages.
    flow_by_id = {
        flow.get("flow_id"): flow
        for flow in (capture.n2 or {}).get("flows") or []
        if flow.get("flow_id") is not None
    }
    sbi_messages = (capture.sbi or {}).get("messages") or []
    for procedure_index, procedure in enumerate(
        (capture.sbi or {}).get("procedures") or []
    ):
        flow = flow_by_id.get(procedure.get("flow_id"))
        if flow is None:
            continue
        ips = {
            ip
            for ref in flow.get("sbi_refs") or []
            if isinstance(ref, int) and 0 <= ref < len(sbi_messages)
            for ip in (
                sbi_messages[ref].get("src_ip"),
                sbi_messages[ref].get("dst_ip"),
            )
            if ip
        }
        for partner_ip in list(partners):
            if partner_ip in ips:
                partners[partner_ip] = _attributed(
                    partners[partner_ip],
                    f"sbi/procedures/{procedure_index}",
                    procedure,
                )

    return BlastResult(
        target,
        tuple(sorted(partners.values(), key=lambda nf: (nf.role, nf.ip))),
        len(unknown_ips),
        tuple(unknown_ips.values()),
    )
