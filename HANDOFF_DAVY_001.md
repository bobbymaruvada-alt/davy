# HANDOFF_DAVY_001

STATUS: COMPLETE

## Summary

Built DAVY v0.1 as a standalone local ChatGPT <-> Codex relay under `~/AI/davy`. It is file-backed, has no network automation, and exposes a simple CLI for creating runs, preparing Codex prompt artifacts, recording Codex output, preparing the next ChatGPT review artifact, and listing status.

## Files Created

- `README.md`
- `pyproject.toml`
- `davy/__init__.py`
- `davy/__main__.py`
- `davy/cli.py`
- `davy/relay.py`
- `tests/test_relay.py`
- `HANDOFF_DAVY_001.md`

## Validation

- `python3 -m pytest -q`

## Remaining Risks

- DAVY is intentionally manual; it prepares artifacts but does not send to ChatGPT or Codex.
- Transcript history is stored inside `state.json`; very large transcripts may eventually need separate append-only transcript storage.
- No shell entry point is installed; use `python -m davy` from the DAVY directory for v0.1.

## Recommended DAVY-002

Add a small `davy captain` review command that shows pending approval points and lets Bobby mark a run `needs_captain`, `complete`, or `failed` without editing JSON by hand.
