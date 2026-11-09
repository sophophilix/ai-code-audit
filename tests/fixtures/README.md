# Planted fixtures

Each folder is a tiny target with one planted case and an `expected.json` that
lists what the kit must find and what it must not find (ADR 0004 D11). The
fixtures test the kit's deterministic Python; the seeded-issue evals still
measure the agents. Change an `expected.json` only with a reason in the commit.
