# HANDOFF_DAVY_003

STATUS: COMPLETE

## Summary

Added a read-only transcript command for DAVY runs. The command shows run identity, current status, core artifacts, latest Codex output, next ChatGPT review text, transcript entries through JSON output, and the event trail with timestamps and reason/message details.

## Files Changed

- `README.md`
- `davy/cli.py`
- `davy/relay.py`
- `tests/test_relay.py`
- `HANDOFF_DAVY_003.md`

## Validation

- `python3 -m unittest discover -s tests -q`
- `/Users/bobbymaruvada/AI/mission-control/.venv/bin/python -m pytest -q`
- CLI smoke flow for `transcript` after create, record-codex, and captain status changes.

## Remaining Risks

- Human-readable transcript output includes the main artifacts and event trail, while full transcript entry metadata is most complete in `--json` output.
- Very large artifact contents are printed inline; pagination or truncation may be useful later.

## Recommended DAVY-004

Add a small `davy open <run-id>` helper that prints the run directory and key artifact paths, making it easier to hand files to external tools without browsing the filesystem manually.
