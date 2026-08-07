"""Public-RLVR reward wrapper using visible tests as the sole scoring source."""

from __future__ import annotations

from code_verifier.rewards.common import RewardContractError, _require_executor, compute_code_rewards


def public_code_reward(
    completions: object,
    visible_tests: object,
    function_name: object,
    metadata: object,
    **kwargs: object,
) -> list[float]:
    """Compute Public-RLVR rewards using visible_tests as the only test source."""
    if "train_hidden_tests" in kwargs:
        raise RewardContractError("public reward must not receive train_hidden_tests")
    if "eval_hidden_tests" in kwargs:
        raise RewardContractError("public reward must not receive eval_hidden_tests")
    executor = _require_executor(kwargs.get("executor"))
    rewards, _ = compute_code_rewards(
        completions,
        visible_tests,
        function_name,
        metadata,
        executor,
        mode="public",
    )
    return rewards
