# DAVY

DAVY is a small local relay for reducing manual ChatGPT <-> Codex copy/paste.

Role model:

- Bobby is the captain and approval gate.
- ChatGPT plans and reviews.
- Codex implements.
- DAVY stores transport state and durable artifacts.

DAVY v0.1 has no network service and does not auto-send to ChatGPT or Codex.

## Usage

Initialize the local workspace:

```bash
python -m davy init
```

Create a run from a ChatGPT prompt file:

```bash
python -m davy create --prompt-file prompt.md
```

Show or prepare the Codex prompt artifact:

```bash
python -m davy codex-prompt <run-id>
```

Record Codex output:

```bash
python -m davy record-codex <run-id> --file codex-output.md
```

Show the next ChatGPT review artifact:

```bash
python -m davy next-chatgpt <run-id>
```

Inspect status and transcript:

```bash
python -m davy status <run-id>
python -m davy status <run-id> --json
python -m davy list
python -m davy transcript <run-id>
python -m davy transcript <run-id> --json
python -m davy protocol <run-id>
python -m davy next-codex <run-id>
python -m davy launch-codex <run-id>
python -m davy launch-codex <run-id> --execute
```

Mark captain-controlled outcomes without editing JSON:

```bash
python -m davy captain <run-id> --reason "Needs Bobby approval"
python -m davy complete <run-id> --reason "Reviewed and accepted"
python -m davy fail <run-id> --reason "Blocked by failing validation"
```

All run data is stored under `runs/<run-id>/`.


## Relay Status

`python -m davy status <run-id>` reads `protocol.json` and reports the current relay status, whether `codex_output.md` and `next_chatgpt.md` exist, the latest `launch.json` result when present, missing relay files, and the next expected operator action. Use `--json` for the same operator-facing view as structured data.

The status view also runs relay integrity checks. It reports missing or unreadable `protocol.json`, unknown status values, run-id mismatches, missing artifacts required by the current status, and failed runs without error metadata. Integrity failures are included in both human and JSON output.

## Protocol

Every run has `runs/<run-id>/protocol.json`, a deterministic JSON summary for ChatGPT/Codex handoff state. It is synchronized whenever DAVY creates a run, records output, shows handoff artifacts, or changes captain status. Existing runs without `protocol.json` are backfilled when `python -m davy protocol <run-id>` is run.

## Next Codex Prompt

`python -m davy next-codex <run-id>` reads `protocol.json` and writes `runs/<run-id>/next_codex_prompt.md`. The generated prompt includes DAVY's execution policy and the structured engineering state from the protocol. If `requires_captain` is true, DAVY refuses to generate the prompt and prints the captain reason.

## Codex Launch Adapter

`python -m davy launch-codex <run-id>` validates `protocol.json` and `next_codex_prompt.md`, prints the exact Codex command, records a launch event, and writes `runs/<run-id>/launch.json` without executing anything.

`python -m davy launch-codex <run-id> --execute` runs the Codex command with `next_codex_prompt.md` as stdin, captures stdout/stderr where possible, records launch start/finish events, and stores exit metadata in `launch.json`. DAVY refuses launch when captain approval is required, when the run is complete or failed, or when required launch artifacts are missing.

## Launch Result Intake

When `python -m davy launch-codex <run-id> --execute` exits with code `0` and captured stdout is non-empty, DAVY imports that stdout into `runs/<run-id>/codex_output.md`, regenerates `next_chatgpt.md`, refreshes `protocol.json`, and sets the run status to `ready_for_chatgpt`. Failed launches do not overwrite prior Codex output; DAVY records launch error metadata and marks the run `failed`. Dry-run launch behavior is unchanged.
