"""Strict experiment analysis contracts."""

from code_verifier.analysis.compare import (
    FailureCandidate,
    PairedComparison,
    compare_evaluation_records,
    select_failure_candidates,
)
from code_verifier.analysis.experiment import (
    AnalysisConfig,
    AnalysisError,
    AnalysisInputs,
    load_analysis_config,
    load_analysis_inputs,
)
from code_verifier.analysis.report import (
    AnalysisSummary,
    CostRow,
    TrainingCurveRow,
    analyze_experiment,
    build_cost_row,
    load_manual_labels,
    load_training_curve_rows,
)

__all__ = [
    "AnalysisConfig",
    "AnalysisError",
    "AnalysisInputs",
    "AnalysisSummary",
    "CostRow",
    "FailureCandidate",
    "PairedComparison",
    "TrainingCurveRow",
    "analyze_experiment",
    "build_cost_row",
    "compare_evaluation_records",
    "load_analysis_config",
    "load_analysis_inputs",
    "load_manual_labels",
    "load_training_curve_rows",
    "select_failure_candidates",
]
