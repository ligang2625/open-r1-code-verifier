"""Training integration contracts for CodeVerifier."""

from code_verifier.training.grpo import (
    GRPOCheckpointIdentity,
    GRPOTrainingConfig,
    GRPOTrainingError,
    GRPOTrainingSummary,
    build_grpo_reward_callback,
    grpo_evaluation_checkpoint_id,
    grpo_training_config_from_mapping,
    load_completed_grpo_checkpoint,
    load_grpo_training_config,
    run_grpo_training,
    validate_grpo_artifact_pair,
    validate_grpo_config_pair,
    validate_grpo_training_hardware,
)
from code_verifier.training.grpo_data import GRPODataError, build_grpo_dataset
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
    "GRPOCheckpointIdentity",
    "GRPODataError",
    "GRPOTrainingConfig",
    "GRPOTrainingError",
    "GRPOTrainingSummary",
    "SFTCheckpointIdentity",
    "SFTDataError",
    "SFTExample",
    "SFTTrainingConfig",
    "SFTTrainingError",
    "SFTTrainingSummary",
    "build_grpo_dataset",
    "build_grpo_reward_callback",
    "build_sft_dataset",
    "grpo_evaluation_checkpoint_id",
    "grpo_training_config_from_mapping",
    "load_completed_grpo_checkpoint",
    "load_completed_sft_checkpoint",
    "load_grpo_training_config",
    "load_sft_training_config",
    "run_grpo_training",
    "run_sft_training",
    "validate_grpo_artifact_pair",
    "validate_grpo_config_pair",
    "validate_grpo_training_hardware",
    "validate_sft_record",
    "validate_sft_training_hardware",
]
