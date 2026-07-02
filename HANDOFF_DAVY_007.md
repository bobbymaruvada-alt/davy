# HANDOFF_DAVY_007

STATUS: COMPLETE

## Summary

Extended `launch-codex --execute` with launch-result intake. Successful launches with non-empty stdout now import captured Codex output into `codex_output.md`, regenerate `next_chatgpt.md`, refresh `protocol.json`, and set status to `ready_for_chatgpt`. Failed launches preserve existing output, persist stderr/error metadata, and mark the run failed. Dry-run and manual `record-codex` flows remain intact.

## Files Changed

- `README.md`
- `davy/relay.py`
- `tests/test_relay.py`
- `HANDOFF_DAVY_007.md`

## Validation

- `python3 -m unittest discover -s tests -q`
- `/Users/bobbymaruvada/AI/mission-control/.venv/bin/python -m pytest -q`
- CLI smoke flow for successful stdout intake and failed-launch preservation.

## Remaining Risks

- DAVY imports all successful stdout as Codex output; noisy tool output from Codex would be carried into the relay.
- Failed launches currently mark the run `failed`; a future captain policy may distinguish retryable failures from terminal failures.

## Recommended DAVY-008

Add lightweight launch output classification so DAVY can separate human-readable Codex result text from command/log noise before importing stdout into `codex_output.md`.
