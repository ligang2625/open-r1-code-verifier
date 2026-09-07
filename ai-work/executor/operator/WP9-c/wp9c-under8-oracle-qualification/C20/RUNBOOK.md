# WP9-c C20 — CLOSED / verified

C20 is complete and must not be rerun. Its checkpoint is `completed_verified`, so the old C20 shell runner now fails closed.

Verified result from 638 under8 existing-test source-oracle qualification jobs:

- `oracle_pair_qualified`: 615
- `oracle_pair_fail`: 23
- `infrastructure_blocked`: 0
- total source-solution executions: 2118
- Piston runtime: Python 3.10.0
- 23 correctness failures are dropped without backfill

Source qualified counts:

- BAAI/TACO: 552
- codeparrot/apps: 62
- deepcoder-taco: 1

Verified artifacts:

- report SHA256: `02f372efd135a77ffcac6fcabc5bfbe6703be369ee9b905848bae904bc2fb6bb`
- checkpoint results SHA256: `c942932c9d36a06584649672642cfa6c194c213050106518626bbf5baa265ea8`
- candidate results SHA256: `4300c1ad03377b95ed9280d863ffe54b05dd6b8bf6eae010c6f86f3ee639b1a8`
- qualified manifest SHA256: `e13c9f06be73b9b010d623fe1fe72d7866ea057bc18405e237acb4c5972b5bed`
- failure manifest SHA256: `2d9fba5fdc8d83ef210c3a6131bd10818d89790f80d20b31ee62b928b9e218c8`
- log SHA256: `bb2c629709a8246306ae55ebffc24754954a070785b2573ab00f2db3a692576f`
- closed checkpoint SHA256: `ee5f2659537fcd0c169e1f632b318eb32e5b9b1a65cd421ba08f11504cfc81f8`

Current work has moved to C21 deterministic proposal consensus. See:

`ai-work/executor/operator/WP9-c/wp9c-under8-proposal-consensus/C21/RUNBOOK.md`
