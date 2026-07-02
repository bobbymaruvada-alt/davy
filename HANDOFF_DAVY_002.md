# HANDOFF_DAVY_002

STATUS: COMPLETE

## Summary

Added explicit captain status controls for DAVY relay runs. Bobby can now mark a run as needing captain input, complete, or failed from the CLI with an optional reason, and each change is persisted to `state.json` plus `events.jsonl` without changing transcript history.

## Files Changed

- `README.md`
- `davy/cli.py`
- `davy/relay.py`
- `tests/test_relay.py`
- `HANDOFF_DAVY_002.md`

## Validation

- `python3 -m unittest discover -s tests -q`
- `/Users/bobbymaruvada/AI/mission-control/.venv/bin/python -m pytest -q`

## Remaining Risks

- Captain controls are status-only. They do not yet prompt for or enforce structured approval gates.
- Reason text is stored in events but not surfaced in status/list output yet.

## Recommended DAVY-003

Add a `davy transcript <run-id>` command that prints the full ordered transcript and event trail for review without opening JSON files.
