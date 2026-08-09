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

__all__ = [
    "CompletionGenerator",
    "EvaluationAggregate",
    "EvaluationAggregateSummary",
    "EvaluationMetrics",
    "GenerationConfig",
    "GenerationError",
    "GenerationResult",
    "MetricsError",
    "TransformersCompletionGenerator",
    "aggregate_evaluation_records",
    "aggregate_evaluation_run",
    "build_evaluation_prompt",
    "evaluation_aggregate_to_mapping",
    "validate_generation_config",
]
