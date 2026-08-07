"""Hidden-RLVR reward wrapper using train-hidden tests as the sole scoring source."""

from __future__ import annotations

from code_verifier.rewards.common import RewardContractError, _require_executor, compute_code_rewards


def hidden_code_reward(
    completions: object,
    train_hidden_tests: object,
    function_name: object,
    metadata: object,
    **kwargs: object,
) -> list[float]:
    """Compute Hidden-RLVR rewards using train_hidden_tests as the only scoring test source."""
    if "eval_hidden_tests" in kwargs:
        raise RewardContractError("hidden reward must not receive eval_hidden_tests")
    executor = _require_executor(kwargs.get("executor"))
    rewards, _ = compute_code_rewards(
        completions,
        train_hidden_tests,
        function_name,
        metadata,
        executor,
        mode="hidden",
    )
    return rewards
