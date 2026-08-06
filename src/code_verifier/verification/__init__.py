"""Public WP4-a verification contracts and orchestration."""

from code_verifier.verification.result_types import (
    FailureCounts,
    VerificationContractError,
    VerificationResult,
    validate_verification_result,
    verification_result_to_mapping,
)
from code_verifier.verification.verifier import verify_completion

__all__ = [
    "FailureCounts",
    "VerificationContractError",
    "VerificationResult",
    "validate_verification_result",
    "verification_result_to_mapping",
    "verify_completion",
]
