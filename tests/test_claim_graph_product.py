from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from veritas.claim_reconstruction import (
    ClaimObjectReconstructionError,
    reconstruct_statistical_object,
)
from veritas.claims import StatisticalClaimGraph
from veritas.extraction import ExtractionCandidate
from veritas.harness.claim_graph_product import (
    project_claim_graph,
    register_claim_graph_routes,
)
from veritas.harness.tools import PaperToolbox
from veritas.models import SourceLocation

ROOT = Path(__file__).resolve().parents[1]


def _candidate(
    *,
    family: str,
    parser_id: str,
    raw: str,
    normalized: str,
    field: str,
    score: float = 0.1,
) -> ExtractionCandidate:
    return ExtractionCandidate(
        parser_id=parser_id,
        parser_family=family,
        raw=raw,
        normalized_value=normalized,
        nonconformity_score=score,
        source=SourceLocation(
            artifact_id="paper-abc",
            page=3,
            table="Table 4",
            row="Minimum wage",
            column=field,
            text_quote=raw,
        ),
    )


def _persisted_graph() -> dict[str, object]:
    field_candidates = {
        "beta": (
            _candidate(
                family="mupdf_native",
                parser_id="mupdf",
                raw="-0.021",
                normalized="-0.021",
                field="beta",
                score=0.08,
            ),
            _candidate(
                family="pdfminer_native",
                parser_id="pdfminer",
                raw="-0.021",
                normalized="-0.021",
                field="beta",
                score=0.12,
            ),
        ),
        "se": (
            _candidate(
                family="mupdf_native",
                parser_id="mupdf",
                raw="0.026",
                normalized="0.026",
                field="se",
            ),
            _candidate(
                family="pdfminer_native",
                parser_id="pdfminer",
                raw="0.026",
                normalized="0.026",
                field="se",
            ),
        ),
        "t_stat": (
            _candidate(
                family="mupdf_native",
                parser_id="mupdf",
                raw="-0.808",
                normalized="-0.808",
                field="t_stat",
            ),
            _candidate(
                family="pdfminer_native",
                parser_id="pdfminer",
                raw="-0.808",
                normalized="-0.808",
                field="t_stat",
            ),
        ),
        "p_value": (
            _candidate(
                family="mupdf_native",
                parser_id="mupdf",
                raw="0.419",
                normalized="0.419",
                field="p_value",
            ),
            _candidate(
                family="pdfminer_native",
                parser_id="pdfminer",
                raw="0.419",
                normalized="0.419",
                field="p_value",
            ),
        ),
    }
    semantic_candidates = {
        "inference_distribution": (
            _candidate(
                family="mupdf_native",
                parser_id="mupdf",
                raw="normal",
                normalized="normal",
                field="distribution",
            ),
            _candidate(
                family="pdfminer_native",
                parser_id="pdfminer",
                raw="normal",
                normalized="normal",
                field="distribution",
            ),
        )
    }
    bundle = SimpleNamespace(
        artifact_id="paper-abc",
        artifact_sha256="a" * 64,
        field_candidates=field_candidates,
        semantic_candidates=semantic_candidates,
        source=SourceLocation(
            artifact_id="paper-abc",
            page=3,
            table="Table 4",
            row="Minimum wage",
        ),
    )
    return PaperToolbox._regression_claim_graph(
        bundle,
        row_label="Minimum wage",
        consensus={
            "beta": "-0.021",
            "se": "0.026",
            "t_stat": "-0.808",
            "p_value": "0.419",
        },
        distribution_consensus="normal",
    )


def _annotated_result() -> dict[str, object]:
    return {
        "claim_graph": _persisted_graph(),
        "checks": [
            {
                "check_id": "p_value",
                "status": "fail",
                "finding": {
                    "finding_id": "finding-1",
                    "title": "Regression reporting contradiction",
                    "explanation": "Reported p-value is incompatible with the displayed statistic.",
                    "severity": "contradiction",
                    "source": {
                        "artifact_id": "paper-abc",
                        "page": 3,
                        "table": "Table 4",
                        "row": "Minimum wage",
                    },
                },
            }
        ],
    }


def test_interactive_graph_persists_object_provenance_without_inventing_claims():
    graph = StatisticalClaimGraph.from_dict(_persisted_graph())

    assert set(graph.artifacts) == {"paper-abc"}
    assert graph.claims == {}
    assert graph.edges == []
    assert set(graph.objects) == {"paper-abc:Minimum wage"}
    regression = graph.objects["paper-abc:Minimum wage"]
    assert regression.object_type == "RegressionResult"
    assert regression.fields["beta"].raw == "-0.021"
    assert regression.fields["beta"].source.column == "beta"
    assert regression.fields["beta"].extraction_confidence == 0.0
    assert regression.fields["p_value"].comparison_operator is not None

    with pytest.raises(ClaimObjectReconstructionError, match="p_value_adjusted"):
        reconstruct_statistical_object(graph, regression.object_id)


def test_product_projection_validates_graph_and_exposes_authority_boundary():
    payload = project_claim_graph(
        {
            "audit_id": "audit-1",
            "latest_result": {"claim_graph": _persisted_graph()},
        }
    )

    assert payload["available"] is True
    assert payload["authority"] == {
        "source": "persisted_statistical_claim_graph",
        "client_inferred_edges": False,
        "publication_claim_bound": False,
        "claim_edges_persisted": 0,
        "detector_annotations_are_graph_edges": False,
    }
    assert payload["counts"] == {
        "artifacts": 1,
        "claims": 0,
        "objects": 1,
        "evidence_nodes": 0,
        "edges": 0,
        "detector_annotations": 0,
    }
    assert payload["reconstruction"]["paper-abc:Minimum wage"]["available"] is False


def test_detector_findings_remain_navigation_annotations_not_graph_edges():
    payload = project_claim_graph(
        {
            "audit_id": "audit-1",
            "latest_result": _annotated_result(),
        }
    )

    graph = StatisticalClaimGraph.from_dict(payload["graph"])
    assert graph.edges == []
    assert graph.claims == {}
    assert payload["authority"]["detector_annotations_are_graph_edges"] is False
    assert payload["counts"]["detector_annotations"] == 1
    annotation = payload["annotations"][0]
    assert annotation["finding_id"] == "finding-1"
    assert annotation["field"] == "p_value"
    assert annotation["graph_edge"] is False


def test_product_projection_refuses_missing_or_invalid_graphs():
    missing = project_claim_graph({"audit_id": "old", "latest_result": {"checks": []}})
    assert missing["available"] is False
    assert missing["state"] == "not_persisted"
    assert "will not infer claim-object edges" in str(missing["reason"])

    invalid = project_claim_graph(
        {
            "audit_id": "bad",
            "latest_result": {
                "claim_graph": {
                    "artifacts": {},
                    "claims": {},
                    "objects": {},
                    "evidence_nodes": {},
                    "edges": [
                        {
                            "source_id": "missing",
                            "target_id": "other",
                            "relation": "supports",
                        }
                    ],
                }
            },
        }
    )
    assert invalid["available"] is False
    assert invalid["state"] == "invalid"
    assert invalid["graph"] is None


def test_claim_graph_route_uses_server_projection_and_404s_unknown_audit():
    class Harness:
        def get_audit(self, audit_id: str):
            if audit_id == "missing":
                raise FileNotFoundError("audit not found")
            return {
                "audit_id": audit_id,
                "latest_result": {"claim_graph": _persisted_graph()},
            }

    app = FastAPI()
    register_claim_graph_routes(app, Harness())
    client = TestClient(app)

    response = client.get("/api/v1/audits/audit-1/claim-graph")
    assert response.status_code == 200
    assert response.json()["available"] is True
    assert response.json()["authority"]["client_inferred_edges"] is False
    assert client.get("/api/v1/audits/missing/claim-graph").status_code == 404


def test_claim_graph_frontend_consumes_validated_endpoint_instead_of_latest_result_projection():
    source = (ROOT / "src/veritas/harness/static/claim-graph.js").read_text(encoding="utf-8")
    annotations = (ROOT / "src/veritas/harness/static/claim-graph-annotations.js").read_text(
        encoding="utf-8"
    )
    index = (ROOT / "src/veritas/harness/static/index.html").read_text(encoding="utf-8")
    sw = (ROOT / "src/veritas/harness/static/sw.js").read_text(encoding="utf-8")
    web = (ROOT / "src/veritas/harness/web.py").read_text(encoding="utf-8")

    endpoint = "/api/v1/audits/${encodeURIComponent(auditId)}/claim-graph"
    assert endpoint in source
    assert endpoint in annotations
    assert "latest_result" not in source
    assert "consensus" not in source
    assert "checkItems" not in source
    assert "No publication claim identity bound" in source
    assert "data-cg-persisted-edge" in source
    assert '"source address"' not in source
    assert '"field"));' not in source
    assert "detector_annotations_are_graph_edges !== false" in annotations
    assert "annotation.graph_edge !== false" in annotations
    assert "Detector annotations never become ClaimEdges" in annotations
    assert "graph.dataset.cgAnnotationFindingId === annotationState.findingId" in annotations
    assert "graph.dataset.cgAnnotationFindingId = annotation.finding_id" in annotations
    assert "root.querySelector(\".ah-tabs [data-ah-tab='source']\")?.click();" in annotations
    assert "const freshRoot = auditRoot() || root;" in annotations
    assert index.index("/static/claim-graph.js") < index.index("/static/claim-graph-annotations.js")
    assert index.index("/static/claim-graph-annotations.js") < index.index(
        "/static/finding-navigation.js"
    )
    assert 'const CACHE_REVISION = "claim-graph-authority-2";' in sw
    assert '"/static/claim-graph-annotations.js"' in sw
    assert "register_claim_graph_routes(app, app.state.harness)" in web
