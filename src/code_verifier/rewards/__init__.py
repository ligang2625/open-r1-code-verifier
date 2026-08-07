"""Public WP4 reward contracts and Public/Hidden wrappers."""

from __future__ import annotations

from code_verifier.rewards.common import RewardContractError, compute_code_rewards
from code_verifier.rewards.hidden_reward import hidden_code_reward
from code_verifier.rewards.public_reward import public_code_reward

__all__ = [
    "RewardContractError",
    "compute_code_rewards",
    "hidden_code_reward",
    "public_code_reward",
]
