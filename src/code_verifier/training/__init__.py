"""Training integration contracts for CodeVerifier."""

from code_verifier.training.sft import (
    SFTCheckpointIdentity,
    SFTTrainingConfig,
    SFTTrainingError,
    SFTTrainingSummary,
    load_completed_sft_checkpoint,
    load_sft_training_config,
    run_sft_training,
    validate_sft_training_hardware,
)
from code_verifier.training.sft_data import SFTDataError, SFTExample, build_sft_dataset, validate_sft_record

__all__ = [
    "SFTCheckpointIdentity",
    "SFTDataError",
    "SFTExample",
    "SFTTrainingConfig",
    "SFTTrainingError",
    "SFTTrainingSummary",
    "build_sft_dataset",
    "load_completed_sft_checkpoint",
    "load_sft_training_config",
    "run_sft_training",
    "validate_sft_record",
    "validate_sft_training_hardware",
]
