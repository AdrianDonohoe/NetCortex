"""The specgraph fallback: reference partners from co-mentioned SBI entities."""

from impact.specgraph import (
    RefPartner,
    SpecGraphState,
    co_mentioned,
    reference_partners,
    sbi_entities,
    sbi_family,
)


def _entity(**overrides):
    entity = {
        "id": "message:29502:8.2.2.2.2:Nsmf_PDUSession_CreateSMContext",
        "type": "message",
        "spec": "29502",
        "name": "Nsmf_PDUSession_CreateSMContext",
        "clause": "8.2.2.2.2",
        "protocol": "SBI",
    }
    return {**entity, **overrides}


def _graph(entities=(), edges=(), path="specgraph.json", **overrides):
    return SpecGraphState(path, tuple(entities), tuple(edges), **overrides)


def test_sbi_family_maps_a_service_name_to_its_nf():
    assert sbi_family(_entity()) == "Nsmf"
    assert sbi_family(_entity(name="Nnssf_NSSelection_Get",
                              id="message:29531:8.1:Nnssf_NSSelection_Get")) == "Nnssf"


def test_sbi_family_rejects_non_service_names():
    assert sbi_family(_entity(name="REGISTRATION REQUEST")) is None
    assert sbi_family(_entity(name="N1 something")) is None


def test_co_mentioned_returns_the_neighbors_of_an_entity():
    namf = _entity(name="Namf_Communication_N1N2MessageTransfer",
                   id="message:29518:5.2:Namf_Communication_N1N2MessageTransfer")
    graph = _graph(
        entities=(_entity(), namf),
        edges=(
            {"src": _entity()["id"], "dst": namf["id"], "kind": "co_mentioned"},
        ),
    )
    assert co_mentioned(graph, (_entity()["id"],)) == (namf,)


def test_reference_partners_derive_from_co_mentioned_sbi_messages():
    namf = _entity(name="Namf_Communication_N1N2MessageTransfer",
                   id="message:29518:5.2:Namf_Communication_N1N2MessageTransfer")
    clause = {**_entity(), "type": "clause", "name": "PDU Session Establishment"}
    graph = _graph(
        entities=(_entity(), namf, clause),
        edges=(
            {"src": _entity()["id"], "dst": namf["id"], "kind": "co_mentioned"},
            {"src": _entity()["id"], "dst": clause["id"], "kind": "contains"},
        ),
    )
    partners = reference_partners(graph, "SMF")
    assert partners == (
        RefPartner("AMF", (namf["id"],)),
    )


def test_reference_partners_excludes_the_targets_own_family():
    other = _entity(name="Nsmf_PDUSession_UpdateSMContext",
                    id="message:29502:8.2.2.2.3:Nsmf_PDUSession_UpdateSMContext")
    graph = _graph(
        entities=(_entity(), other),
        edges=(
            {"src": _entity()["id"], "dst": other["id"], "kind": "co_mentioned"},
        ),
    )
    assert reference_partners(graph, "SMF") == ()


def test_empty_or_unconsulted_graphs_derive_nothing():
    assert reference_partners(_graph(), "SMF") == ()
    absent = _graph(path="absent.json", exists=False)
    assert reference_partners(absent, "SMF") == ()
    assert absent.describe() == "absent.json does not exist"
