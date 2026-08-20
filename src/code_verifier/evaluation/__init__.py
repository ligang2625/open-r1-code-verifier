"""Public evaluation APIs for deterministic pass@1 runs."""

from code_verifier.evaluation.generate import (
    CompletionGenerator,
    GenerationConfig,
    GenerationError,
    GenerationResult,
    TransformersCompletionGenerator,
    build_evaluation_prompt,
    validate_generation_config,
)
from code_verifier.evaluation.metrics import (
    EvaluationAggregate,
    EvaluationAggregateSummary,
    EvaluationMetrics,
    MetricsError,
    aggregate_evaluation_records,
    aggregate_evaluation_run,
    evaluation_aggregate_to_mapping,
)
from code_verifier.evaluation.staged import (
    EvaluationVerificationSummary,
    GenerationBundleIdentity,
    GenerationBundleRecord,
    GenerationBundleSource,
    GenerationBundleSummary,
    load_completed_generation_bundle,
    load_generation_bundle_source,
    run_generation_bundle,
    run_verification_from_generation_bundle,
)

__all__ = [
    "CompletionGenerator",
    "EvaluationAggregate",
    "EvaluationAggregateSummary",
    "EvaluationMetrics",
    "EvaluationVerificationSummary",
    "GenerationBundleIdentity",
    "GenerationBundleRecord",
    "GenerationBundleSource",
    "GenerationBundleSummary",
    "GenerationConfig",
    "GenerationError",
    "GenerationResult",
    "MetricsError",
    "TransformersCompletionGenerator",
    "aggregate_evaluation_records",
    "aggregate_evaluation_run",
    "build_evaluation_prompt",
    "evaluation_aggregate_to_mapping",
    "load_completed_generation_bundle",
    "load_generation_bundle_source",
    "run_generation_bundle",
    "run_verification_from_generation_bundle",
    "validate_generation_config",
]
