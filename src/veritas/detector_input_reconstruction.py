from __future__ import annotations

from .claim_design_reconstruction import reconstruct_design_descriptor
from .claim_reconstruction import ClaimObjectReconstructionError, reconstruct_statistical_object
from .claims import StatisticalClaimGraph

_DESIGN_OBJECT_TYPES = {"DesignDescriptor", "DIDDesign", "IVDesign", "RDDDesign"}


def reconstruct_detector_input(graph: StatisticalClaimGraph, object_id: str) -> object:
    """Rebuild any currently supported detector input from serialized graph state.

    Statistical objects use the established claim-reconstruction boundary;
    design descriptors use the stricter design schema. No parser/ingestion state
    is consulted and unsupported object types fail closed.
    """

    try:
        node = graph.objects[object_id]
    except KeyError as exc:
        raise ClaimObjectReconstructionError(
            f"claim graph has no statistical object {object_id!r}"
        ) from exc
    if node.object_type in _DESIGN_OBJECT_TYPES:
        return reconstruct_design_descriptor(node)
    return reconstruct_statistical_object(graph, object_id)
