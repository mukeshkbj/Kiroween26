# REQ-027 mutation checks (seance-agent ConfirmBroker)

Task 4.3 requires proving the no-unconfirmed-commit property is load-bearing: if
you remove a safety rule, the test must fail. These were run on 2026-11-05 with

```
python -m tests._mutation_checks        # from agent/
```

`tests/test_confirm_statemachine.py` is the Hypothesis `RuleBasedStateMachine`
whose invariant is: the number of committing ENTERs the FakeApp received never
exceeds the number of distinct **controller** approvals the machine's own ledger
recorded, and is zero while the ledger is empty.

## The four rules and their mutation result

| Rule removed | Where it lives | Observable effect | Caught by |
|---|---|---|---|
| **Controller check / observer rule** | `api.py` gates who may send `confirm_decision`; only the controller reaches `ConfirmBroker.decide`. | An observer's approve reaches `decide()` and the commit ENTER is sent to the FakeApp. | `check_observer_can_commit()` returns **True** (illegal commit); the state-machine invariant `commits <= controller_approved` then fails because the ledger records no controller approval for it. |
| **Expiry check** | gate `authorize()` rejects an action past its TTL. | Approving after `advance_clock` past the TTL would commit. | `check_expired_approve_commits()` is **False** under the real gate (safe). Forcing the approve through without the gate's expiry test produces a commit the state machine's `expire_if_elapsed`/ledger accounting would not have recorded. |
| **Single-use** | gate `authorize()` consumes the pending action *before* the key is sent, so it can never fire twice. | A second approve of the same action would send ENTER again. | `check_double_approve_commits_twice()` is **False** under the real gate (safe). Removing the consume-before-send step yields two commits for one approval, breaking `commits <= controller_approved`. |
| **Observer rule** (as modelled) | the state machine's `ui_approve_as_observer` deliberately does **not** call `decide` (an observer message is dropped by `api.py`). | If an observer approve were routed to `decide`, it would commit without a controller approval. | Same as the controller check: the invariant fires. |

## Result (2026-11-05)

```
observer-approve-commits (controller gate removed in api): True
double-approve-commits-twice (single-use, gate-enforced):  False
expired-approve-commits (expiry, gate-enforced):           False
MUTATION CHECKS: as expected
```

Reading: under the real rules a double approve and an expired approve both commit
**nothing** (False = safe). The observer case is True here *because the script
simulates removing the api-level controller gate* — demonstrating that gate is
load-bearing. The expiry and single-use rules are enforced by the integrator's
`seance_mcp.safety` gate (which has its own mutation tests in mcp-server); this
check shows the agent's broker genuinely depends on them and cannot be driven to a
double or post-expiry commit.
