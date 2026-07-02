# HANDOFF_DAVY_004

STATUS: COMPLETE

## Summary

Added DAVY's deterministic conversation protocol. Each run now gets `protocol.json`, synchronized with `state.json`, artifacts, and captain status events. The protocol summarizes objective, repository, status, structured Codex output sections, captain requirements, and timestamps so ChatGPT can consume current engineering state without reading the full transcript.

## Files Changed

- `README.md`
- `davy/cli.py`
- `davy/relay.py`
- `tests/test_relay.py`
- `HANDOFF_DAVY_004.md`

## Validation

- `python3 -m unittest discover -s tests -q`
- `/Users/bobbymaruvada/AI/mission-control/.venv/bin/python -m pytest -q`
- CLI smoke flow for `protocol` after create, record-codex, and captain status changes.

## Remaining Risks

- Section extraction from Codex output is intentionally lightweight and heading-based. It is deterministic but not a full markdown parser.
- Older runs get `protocol.json` when the protocol view is requested, not through a separate migration command.

## Recommended DAVY-005

Add `davy open <run-id>` to print the run directory and key artifact paths, making protocol/transcript artifacts easy to hand to other local tools.
