# HANDOFF_DAVY_008

## Summary
Implemented an operator-facing relay status view for DAVY. The existing `status` command now reads `protocol.json`, reports Codex output and next ChatGPT artifact presence, includes the latest Codex launch result when available, lists missing relay files clearly, and gives the next expected action.

## Files Changed
- `davy/relay.py`
- `davy/cli.py`
- `tests/test_relay.py`
- `README.md`
- `HANDOFF_DAVY_008.md`

## Validation
- Added focused status tests for ready/missing-output, ready-for-ChatGPT, failed launch, and CLI JSON output.
- Full DAVY test suite passes.

## Remaining Risks
- Next-action text is intentionally conservative and rule-based; future workflow states may need more specific guidance.

## Recommended DAVY-009
Add launch-result classification so DAVY can distinguish implementation summaries from noisy tool logs before importing Codex stdout into `codex_output.md`.
