from __future__ import annotations

import pytest

from veritas.reproduction_security import (
    AgentDispatchPolicy,
    AgentExecutionLocation,
    ArtifactAccessClassification,
    DataSensitivity,
)


def test_artifact_egress_authorization_requires_real_boolean() -> None:
    with pytest.raises(TypeError, match="external_model_egress_authorized.*boolean"):
        ArtifactAccessClassification(
            artifact_sha256="a" * 64,
            sensitivity=DataSensitivity.PUBLIC,
            external_model_egress_authorized="false",
        )


def test_confidential_compute_approval_requires_real_boolean() -> None:
    with pytest.raises(TypeError, match="confidential_compute_approved.*boolean"):
        AgentDispatchPolicy(
            location=AgentExecutionLocation.TRUSTED_CONFIDENTIAL_COMPUTE,
            provider_id="trusted-runtime",
            confidential_compute_approved="false",
        )


def test_dispatch_enums_must_be_actual_enum_values() -> None:
    with pytest.raises(TypeError, match="sensitivity"):
        ArtifactAccessClassification(
            artifact_sha256="a" * 64,
            sensitivity="public",
        )
    with pytest.raises(TypeError, match="location"):
        AgentDispatchPolicy(
            location="remote_provider",
            provider_id="provider",
        )
