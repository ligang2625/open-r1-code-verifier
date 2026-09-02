"""Public WP4-a verification contracts and orchestration."""

from __future__ import annotations

from code_verifier.verification.result_types import (
    FailureCounts,
    VerificationContractError,
    VerificationResult,
    validate_verification_result,
    verification_result_to_mapping,
)
from code_verifier.verification.verifier import (
    VerificationRequest,
    prevalidate_verification_input,
    verify_completion,
    verify_prevalidated_request,
)

__all__ = [
    "FailureCounts",
    "VerificationContractError",
    "VerificationRequest",
    "VerificationResult",
    "prevalidate_verification_input",
    "validate_verification_result",
    "verification_result_to_mapping",
    "verify_completion",
    "verify_prevalidated_request",
]
