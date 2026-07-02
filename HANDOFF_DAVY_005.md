# HANDOFF_DAVY_005

STATUS: COMPLETE

## Summary

Added DAVY's next Codex prompt generator. `davy next-codex <run-id>` reads `protocol.json`, writes `runs/<run-id>/next_codex_prompt.md`, includes the execution policy automatically, and carries forward objective, status, completed work, files changed, tests, validation, risks, and next recommended task. If captain approval is required, DAVY refuses to generate an executable prompt and reports the captain reason.

## Files Changed

- `README.md`
- `davy/cli.py`
- `davy/relay.py`
- `tests/test_relay.py`
- `HANDOFF_DAVY_005.md`

## Validation

- `python3 -m unittest discover -s tests -q`
- `/Users/bobbymaruvada/AI/mission-control/.venv/bin/python -m pytest -q`
- CLI smoke flow for `next-codex` from protocol state and captain-required refusal.

## Remaining Risks

- The generated prompt quality depends on structured sections being present in Codex output/protocol state. Missing protocol fields fall back to `none` or a conservative next-task instruction.
- The command writes a prompt artifact but does not launch Codex, by design.

## Recommended DAVY-006

Add a `davy open <run-id>` command that prints key artifact paths, including `protocol.json`, `next_codex_prompt.md`, transcript, and run directory for quick local handoff.
