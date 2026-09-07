# WP9-c C21 — CLOSED / verified

C21 deterministic two-oracle proposal consensus is complete and must not be rerun. Its closed checkpoint makes the old manual entry fail closed.

Verified result:

- input: 615
- `consensus_frozen`: 572
- `proposal_consensus_fail`: 43
- `infrastructure_blocked`: 0
- total oracle probe calls: 8121
- every successful row freezes exactly 8 unique tests from the deterministic proposal prefix
- all 43 failures exhausted all frozen proposals
- no backfill

Verified artifacts:

- report SHA256: `45c173edcd986d3aa58dd0cb88b069ba65863d69c37fb0bd078161f7d3431d6f`
- frozen exact8 SHA256: `10e78d00792cfccacf389cdeebcb5ca68ad662cb8ab56308eb7272a9e0260555`
- failures SHA256: `936421c6d063878bc18b42ba420887943653d6432b5670fdd9776d6b537edee5`
- closed checkpoint SHA256: `80bbe53787ae7b59cd3b5b781069d543c806d9f0d991a6ab0d625b4791659af6`

C22 Exact-B is also closed with 572/572 pass. Current work is C23 final formal Piston.
