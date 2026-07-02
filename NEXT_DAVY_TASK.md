# DAVY-008: Relay Status Command

## Objective
Add a simple operator-facing status command for DAVY.

## Command goal
One command should report:
- current relay status
- last Codex launch result
- whether `codex_output.md` exists
- whether `next_chatgpt.md` exists
- next expected action

## Completion criteria
- CLI/status function added
- Reads `protocol.json`
- Reports missing files clearly
- Tests cover ready, failed, and missing-output states
- `pytest` passes
