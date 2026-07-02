# HANDOFF_DAVY_006

STATUS: COMPLETE

## Summary

Added DAVY's Codex launch adapter. `davy launch-codex <run-id>` validates protocol and prompt artifacts, prints the exact Codex command, records dry-run metadata, and does not execute by default. `--execute` runs the command with the generated prompt as stdin, captures stdout/stderr, records start/finish events, and persists exit metadata in `launch.json`. Unsafe states are refused before launch.

## Files Changed

- `README.md`
- `davy/cli.py`
- `davy/relay.py`
- `tests/test_relay.py`
- `HANDOFF_DAVY_006.md`

## Validation

- `python3 -m unittest discover -s tests -q`
- `/Users/bobbymaruvada/AI/mission-control/.venv/bin/python -m pytest -q`
- CLI smoke flow for dry-run launch metadata and captain-required refusal.

## Remaining Risks

- Execute mode assumes the local `codex` CLI accepts prompt text on stdin with `codex exec --cd <repo> -`; this is isolated behind one command builder for future adjustment.
- DAVY records launch output but does not yet import Codex results back into `codex_output.md` automatically.

## Recommended DAVY-007

Add launch-result intake: when a Codex launch exits successfully, optionally record captured stdout as `codex_output.md`, regenerate `next_chatgpt.md`, and refresh `protocol.json` under captain-controlled conditions.
