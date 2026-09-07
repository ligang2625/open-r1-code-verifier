# WP9-c C19 — CLOSED / verified

C19 is complete and must not be rerun. Its checkpoint is `completed_verified`, so the old C19 shell runner now fails closed.

Verified result from 1167 ready-lane Piston jobs:

- `formal_pass`: 1030
- `formal_fail`: 137
- `infrastructure_blocked`: 0
- Piston runtime: Python 3.10.0
- failures are dropped without backfill under `wp9c-reduced-quota-current-viable-v1`

Verified artifacts:

- report SHA256: `3a2b135d61125d794136f2ee4c68b1f436c216398e98ccd47a7b2e14cafcf3c4`
- checkpoint results SHA256: `33099a932f967dd2cf63017add5e2267ff3121a342155e63106a4308853855fb`
- candidate results SHA256: `c924880a3aa271ac14e8f7aa97d0940e49e8349b1b3802d07dce41c3fcb0af9a`
- formal passers SHA256: `aef07311638fd3bd292003aa4097d0adf22ef6ac7e7432530b29546511dccb8f`
- formal failures SHA256: `50df6e4befe85b2f4673d80e0dad914d57051c7f87292502378ffaa10e7a2973`
- infrastructure blocked SHA256: `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`
- log SHA256: `b65e45cd64a5d3b01ef20e7f977aa835bb128d410d5a3a054179f446bed4cb91`
- closed checkpoint SHA256: `e1a828515797b43871606d2a60e6b9dff592986f0ba10b606b8a9f6514fe5ad6`

Current work has moved to C20 under8 existing-test source-oracle qualification. See:

`ai-work/executor/operator/WP9-c/wp9c-under8-oracle-qualification/C20/RUNBOOK.md`
