from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
from typing import Any

from veritas.audit import AuditEngine
from veritas.models import RegressionResult
from veritas.pdf_native import NativePDFSnapshot, parse_pdf_dual
from veritas.pdf_regression import (
    RegressionLocator,
    extract_regression_table,
    parse_reported_number,
)


def _jsonable(value: object) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _source_payload(source: object) -> dict[str, Any]:
    payload = _jsonable(source)
    if not isinstance(payload, dict):
        return {}
    quote = payload.get("text_quote")
    if isinstance(quote, str) and len(quote) > 6000:
        payload["text_quote"] = quote[:6000] + "…"
    return payload


class PaperToolbox:
    """Adapter from the web harness to Veritas' deterministic paper tooling."""

    def parse(self, pdf_bytes: bytes, *, artifact_id: str) -> tuple[NativePDFSnapshot, ...]:
        return tuple(parse_pdf_dual(pdf_bytes, artifact_id=artifact_id))

    def describe(
        self,
        pdf_bytes: bytes,
        *,
        artifact_id: str,
        snapshots: tuple[NativePDFSnapshot, ...] | None = None,
    ) -> dict[str, Any]:
        parsed = snapshots or self.parse(pdf_bytes, artifact_id=artifact_id)
        first = parsed[0]
        table_groups: dict[tuple[object, ...], dict[str, Any]] = {}
        for snapshot in parsed:
            for table in snapshot.tables:
                key = (
                    table.page,
                    table.publication_label,
                    table.caption,
                    table.table_index if table.publication_label is None else None,
                )
                item = table_groups.setdefault(
                    key,
                    {
                        "page": table.page,
                        "label": table.publication_label,
                        "caption": table.caption,
                        "bbox": list(table.bbox),
                        "rows_preview": [
                            [cell for cell in row] for row in table.rows[:4]
                        ],
                        "parsers": [],
                    },
                )
                item["parsers"].append(snapshot.parser_id)

        tables = sorted(
            table_groups.values(),
            key=lambda item: (int(item["page"]), str(item.get("label") or item.get("caption") or "")),
        )
        return {
            "artifact_id": artifact_id,
            "artifact_sha256": first.artifact_sha256,
            "pages": len(first.pages),
            "words": sum(len(page.words) for page in first.pages),
            "blocks": sum(len(page.blocks) for page in first.pages),
            "tables_detected": len(tables),
            "parser_snapshots": [
                {
                    "parser_id": snapshot.parser_id,
                    "parser_family": snapshot.parser_family,
                    "parser_version": snapshot.parser_version,
                    "tables": len(snapshot.tables),
                    "warnings": list(snapshot.warnings),
                }
                for snapshot in parsed
            ],
            "tables": tables,
        }

    def audit_regression(
        self,
        pdf_bytes: bytes,
        *,
        artifact_id: str,
        row_label: str,
        table_label: str | None = None,
        expected_page: int | None = None,
        snapshots: tuple[NativePDFSnapshot, ...] | None = None,
    ) -> dict[str, Any]:
        parsed = snapshots or self.parse(pdf_bytes, artifact_id=artifact_id)
        locator = None
        if table_label is not None or expected_page is not None:
            locator = RegressionLocator(
                table_label=table_label,
                expected_page=expected_page,
            )
        bundle = extract_regression_table(
            parsed,
            variable_label=row_label,
            locator=locator,
        )

        fields = {
            key: self._candidate_payloads(candidates)
            for key, candidates in bundle.field_candidates.items()
        }
        semantics = {
            key: self._candidate_payloads(candidates)
            for key, candidates in bundle.semantic_candidates.items()
        }
        consensus = {
            key: self._consensus_value(candidates)
            for key, candidates in bundle.field_candidates.items()
        }
        distribution = self._consensus_value(
            bundle.semantic_candidates.get("inference_distribution", ())
        )
        if distribution is None:
            distribution = "unknown"

        missing = [
            key
            for key in ("beta", "se", "t_stat")
            if consensus.get(key) is None
        ]
        if bundle.ambiguities or missing:
            reasons = list(bundle.ambiguities)
            if missing:
                reasons.append(
                    "No two-parser consensus for required fields: " + ", ".join(missing)
                )
            return {
                "status": "review_required",
                "row_label": row_label,
                "locator": {
                    "table_label": table_label,
                    "expected_page": expected_page,
                },
                "source": _source_payload(bundle.source),
                "fields": fields,
                "semantics": semantics,
                "consensus": consensus,
                "ambiguities": list(bundle.ambiguities),
                "review_reasons": reasons,
                "verification_coverage": 0.0,
                "review_priority": 0.0,
                "findings": [],
                "checks": [],
                "scope": "interactive_research",
            }

        result = RegressionResult(
            object_id=f"{artifact_id}:{row_label}",
            beta=parse_reported_number(str(consensus["beta"])),
            se=parse_reported_number(str(consensus["se"])),
            t_stat=parse_reported_number(str(consensus["t_stat"])),
            p_value=(
                parse_reported_number(str(consensus["p_value"]))
                if consensus.get("p_value") is not None
                else None
            ),
            inference_distribution=str(distribution),
            source=bundle.source,
        )
        summary = AuditEngine().audit([result])
        checks = [_jsonable(check) for check in summary.checks]
        findings = [_jsonable(finding) for finding in summary.findings]
        failed = sum(1 for check in summary.checks if getattr(check.status, "value", "") == "fail")
        passed = sum(1 for check in summary.checks if getattr(check.status, "value", "") == "pass")
        review = sum(
            1
            for check in summary.checks
            if getattr(check.status, "value", "") == "unverifiable"
        )
        status = "contradiction" if failed else ("review_required" if review else "verified")
        return {
            "status": status,
            "row_label": row_label,
            "locator": {
                "table_label": table_label,
                "expected_page": expected_page,
            },
            "source": _source_payload(bundle.source),
            "fields": fields,
            "semantics": semantics,
            "consensus": {**consensus, "inference_distribution": distribution},
            "ambiguities": list(bundle.ambiguities),
            "verification_coverage": summary.verification_coverage,
            "review_priority": summary.review_priority,
            "findings": findings,
            "checks": checks,
            "counts": {
                "verified": passed,
                "needs_review": review,
                "contradictions": failed,
            },
            "scope": "interactive_research",
        }

    @staticmethod
    def _consensus_value(candidates: object) -> str | None:
        materialized = tuple(candidates)
        families = {candidate.parser_family for candidate in materialized}
        values = {candidate.normalized_value for candidate in materialized}
        if len(families) < 2 or len(values) != 1:
            return None
        return next(iter(values))

    @staticmethod
    def _candidate_payloads(candidates: object) -> list[dict[str, Any]]:
        return [
            {
                "parser_id": candidate.parser_id,
                "parser_family": candidate.parser_family,
                "raw": candidate.raw,
                "normalized_value": candidate.normalized_value,
                "nonconformity_score": candidate.nonconformity_score,
                "source": _source_payload(candidate.source),
            }
            for candidate in candidates
        ]
