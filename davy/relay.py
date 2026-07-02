import json
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


RUNS_DIR = Path("runs")
VALID_STATUSES = {
    "draft",
    "ready_for_codex",
    "waiting_for_codex",
    "ready_for_chatgpt",
    "waiting_for_chatgpt",
    "needs_captain",
    "complete",
    "failed",
}
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
PROTOCOL_VERSION = "1.0"
EXECUTION_POLICY = """Execution Policy

You have standing approval for the following within the target repository:

- Read any file.
- Create, modify, rename, and delete files as required.
- Run Python.
- Run tests.
- Update documentation.
- Create reports.
- Create directories.

You do NOT have approval to:

- Commit or push.
- Install packages.
- Modify repositories outside DAVY.
- Use network services.
- Change system settings.

Continue until the task is complete."""


class DavyError(Exception):
    pass


@dataclass(frozen=True)
class TranscriptEntry:
    role: str
    artifact: str
    text: str
    created_at: str
    source: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class RelayRun:
    run_id: str
    status: str
    created_at: str
    updated_at: str
    transcript: list[dict] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


def init_workspace(root=Path.cwd()):
    root = Path(root)
    (root / RUNS_DIR).mkdir(parents=True, exist_ok=True)
    return root / RUNS_DIR


def create_run(prompt_file, root=Path.cwd(), run_id=None, now=None):
    root = Path(root)
    init_workspace(root)
    prompt_path = resolve_existing_file(prompt_file, root)
    prompt = required_text(prompt_path.read_text(), "ChatGPT prompt")
    created_at = timestamp(now)
    run_id = validate_run_id(run_id or generated_run_id(now))
    run_dir = run_path(run_id, root)
    if run_dir.exists():
        raise DavyError(f"Run already exists: {run_id}")
    run_dir.mkdir(parents=True)

    chatgpt_prompt_path = run_dir / "chatgpt_prompt.md"
    codex_prompt_path = run_dir / "codex_prompt.md"
    chatgpt_prompt_path.write_text(prompt + "\n")
    codex_prompt = render_codex_prompt(run_id, prompt)
    codex_prompt_path.write_text(codex_prompt)

    transcript = [
        TranscriptEntry(
            role="chatgpt",
            artifact="chatgpt_prompt.md",
            text=prompt,
            created_at=created_at,
            source=display_path(prompt_path, root),
        ).to_dict(),
        TranscriptEntry(
            role="davy",
            artifact="codex_prompt.md",
            text=codex_prompt,
            created_at=created_at,
            source="generated",
        ).to_dict(),
    ]
    run = RelayRun(
        run_id=run_id,
        status="ready_for_codex",
        created_at=created_at,
        updated_at=created_at,
        transcript=transcript,
    )
    write_state(run, root)
    append_event(root, run_id, "created", created_at, {"prompt_file": display_path(prompt_path, root)})
    append_event(root, run_id, "codex_prompt_prepared", created_at, {"artifact": "codex_prompt.md"})
    sync_protocol(run_id, root)
    return run


def codex_prompt(run_id, root=Path.cwd(), now=None):
    run = load_run(run_id, root)
    prompt_path = run_path(run_id, root) / "codex_prompt.md"
    if not prompt_path.exists():
        original = artifact_text(run_id, "chatgpt_prompt.md", root)
        prompt_path.write_text(render_codex_prompt(run_id, original))
    if run.status == "ready_for_codex":
        run = replace_run(run, status="waiting_for_codex", updated_at=timestamp(now))
        write_state(run, root)
        append_event(root, run_id, "codex_prompt_shown", run.updated_at, {"artifact": "codex_prompt.md"})
        sync_protocol(run_id, root)
    return prompt_path


def record_codex_output(run_id, output_file, root=Path.cwd(), now=None):
    root = Path(root)
    output_path = resolve_existing_file(output_file, root)
    output = required_text(output_path.read_text(), "Codex output")
    return import_codex_output(
        run_id,
        output,
        root=root,
        source=display_path(output_path, root),
        now=now,
        event_name="codex_output_recorded",
    )


def import_codex_output(run_id, output, root=Path.cwd(), source="launch stdout", now=None, event_name="codex_output_imported"):
    root = Path(root)
    run = load_run(run_id, root)
    output = required_text(output, "Codex output")
    current_time = timestamp(now)
    run_dir = run_path(run_id, root)
    codex_output_path = run_dir / "codex_output.md"
    next_chatgpt_path = run_dir / "next_chatgpt.md"
    codex_output_path.write_text(output + "\n")
    next_chatgpt = render_next_chatgpt(run_id, artifact_text(run_id, "chatgpt_prompt.md", root), output)
    next_chatgpt_path.write_text(next_chatgpt)

    transcript = list(run.transcript)
    transcript.append(TranscriptEntry(
        role="codex",
        artifact="codex_output.md",
        text=output,
        created_at=current_time,
        source=source,
    ).to_dict())
    transcript.append(TranscriptEntry(
        role="davy",
        artifact="next_chatgpt.md",
        text=next_chatgpt,
        created_at=current_time,
        source="generated",
    ).to_dict())
    updated = RelayRun(
        run_id=run.run_id,
        status="ready_for_chatgpt",
        created_at=run.created_at,
        updated_at=current_time,
        transcript=transcript,
    )
    write_state(updated, root)
    append_event(root, run_id, event_name, current_time, {"source": source})
    append_event(root, run_id, "next_chatgpt_prepared", current_time, {"artifact": "next_chatgpt.md"})
    sync_protocol(run_id, root)
    return updated

def next_chatgpt(run_id, root=Path.cwd(), now=None):
    run = load_run(run_id, root)
    path = run_path(run_id, root) / "next_chatgpt.md"
    if not path.exists():
        output = artifact_text(run_id, "codex_output.md", root, required=False)
        path.write_text(render_next_chatgpt(run_id, artifact_text(run_id, "chatgpt_prompt.md", root), output))
    if run.status == "ready_for_chatgpt":
        run = replace_run(run, status="waiting_for_chatgpt", updated_at=timestamp(now))
        write_state(run, root)
        append_event(root, run_id, "next_chatgpt_shown", run.updated_at, {"artifact": "next_chatgpt.md"})
        sync_protocol(run_id, root)
    return path


def status(run_id, root=Path.cwd()):
    return relay_status_view(run_id, root)


def relay_status_view(run_id, root=Path.cwd()):
    root = Path(root)
    run_id = validate_run_id(run_id)
    integrity = integrity_check(run_id, root)
    protocol = integrity.get("protocol") or fallback_protocol_from_state(run_id, root)
    codex_output = artifact_presence(run_id, "codex_output.md", root)
    next_chatgpt_artifact = artifact_presence(run_id, "next_chatgpt.md", root)
    launch = latest_launch_result(run_id, root)
    missing = []
    for artifact in (codex_output, next_chatgpt_artifact):
        if not artifact["exists"]:
            missing.append(artifact["path"])
    return {
        "run_id": run_id,
        "current_status": str(protocol.get("current_status") or "unknown"),
        "requires_captain": bool(protocol.get("requires_captain")),
        "captain_reason": str(protocol.get("captain_reason") or ""),
        "codex_output": codex_output,
        "next_chatgpt": next_chatgpt_artifact,
        "last_launch": launch,
        "missing": missing,
        "integrity": {
            "ok": integrity["ok"],
            "errors": integrity["errors"],
            "warnings": integrity["warnings"],
        },
        "next_expected_action": next_expected_action(protocol, codex_output, next_chatgpt_artifact, launch, integrity),
        "protocol_path": str(Path("runs") / run_id / "protocol.json"),
    }


def integrity_check(run_id, root=Path.cwd()):
    root = Path(root)
    run_id = validate_run_id(run_id)
    errors = []
    warnings = []
    state = read_state_payload(run_id, root, errors)
    protocol = read_protocol_payload(run_id, root, errors)
    launch = latest_launch_result(run_id, root)

    state_status = str((state or {}).get("status") or "")
    protocol_status = str((protocol or {}).get("current_status") or "")
    effective_status = protocol_status or state_status

    if state and state.get("run_id") != run_id:
        add_integrity_error(errors, "state_run_id_mismatch", f"state.json run_id {state.get('run_id')!r} does not match requested run {run_id!r}.", run_id, "state.json")
    if protocol:
        if protocol.get("run_id") != run_id:
            add_integrity_error(errors, "protocol_run_id_mismatch", f"protocol.json run_id {protocol.get('run_id')!r} does not match requested run {run_id!r}.", run_id, "protocol.json")
        if state_status and protocol_status and state_status != protocol_status:
            add_integrity_error(errors, "status_mismatch", f"state.json status {state_status!r} does not match protocol.json status {protocol_status!r}.", run_id, "protocol.json")

    for status_value, artifact in ((state_status, "state.json"), (protocol_status, "protocol.json")):
        if status_value and status_value not in VALID_STATUSES:
            add_integrity_error(errors, "unknown_status", f"{artifact} has unknown status {status_value!r}.", run_id, artifact)

    if effective_status == "ready_for_chatgpt":
        require_artifact(errors, run_id, root, "next_chatgpt.md", "ready_for_chatgpt requires next_chatgpt.md.")
        require_artifact(errors, run_id, root, "codex_output.md", "ready_for_chatgpt requires codex_output.md.")
    if effective_status == "ready_for_codex":
        require_artifact(errors, run_id, root, "chatgpt_prompt.md", "ready_for_codex requires chatgpt_prompt.md.")
        require_artifact(errors, run_id, root, "codex_prompt.md", "ready_for_codex requires codex_prompt.md.")
    if effective_status == "failed" and not failed_error_metadata_exists(run_id, root, launch):
        add_integrity_error(errors, "failed_missing_error_metadata", "failed status requires launch error metadata or a failure reason event.", run_id, "launch.json")
    if effective_status == "complete":
        require_artifact(errors, run_id, root, "codex_output.md", "complete status requires codex_output.md.")

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "state": state,
        "protocol": protocol,
    }


def read_state_payload(run_id, root, errors):
    path = run_path(run_id, root) / "state.json"
    if not path.exists():
        add_integrity_error(errors, "missing_state", "state.json is missing.", run_id, "state.json")
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        add_integrity_error(errors, "unreadable_state", f"state.json is not readable JSON: {error}", run_id, "state.json")
        return None
    if not isinstance(payload, dict):
        add_integrity_error(errors, "invalid_state", "state.json must contain an object.", run_id, "state.json")
        return None
    for field_name in ("run_id", "status", "created_at", "updated_at", "transcript"):
        if field_name not in payload:
            add_integrity_error(errors, "state_missing_field", f"state.json missing field: {field_name}", run_id, "state.json")
    return payload


def read_protocol_payload(run_id, root, errors):
    path = run_path(run_id, root) / "protocol.json"
    if not path.exists():
        add_integrity_error(errors, "missing_protocol", "protocol.json is missing.", run_id, "protocol.json")
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        add_integrity_error(errors, "unreadable_protocol", f"protocol.json is not readable JSON: {error}", run_id, "protocol.json")
        return None
    if not isinstance(payload, dict):
        add_integrity_error(errors, "invalid_protocol", "protocol.json must contain an object.", run_id, "protocol.json")
        return None
    try:
        validate_protocol(payload)
    except DavyError as error:
        add_integrity_error(errors, "invalid_protocol", str(error), run_id, "protocol.json")
    return payload


def fallback_protocol_from_state(run_id, root):
    try:
        run = load_run(run_id, root)
    except DavyError:
        return {
            "run_id": validate_run_id(run_id),
            "current_status": "unknown",
            "requires_captain": False,
            "captain_reason": "",
        }
    return {
        "run_id": run.run_id,
        "current_status": run.status,
        "requires_captain": run.status == "needs_captain",
        "captain_reason": "",
    }


def add_integrity_error(errors, code, message, run_id, artifact):
    errors.append({
        "code": code,
        "message": message,
        "path": str(Path("runs") / validate_run_id(run_id) / artifact),
    })


def require_artifact(errors, run_id, root, artifact, message):
    if not (run_path(run_id, root) / artifact).exists():
        add_integrity_error(errors, f"missing_{artifact.replace('.', '_')}", message, run_id, artifact)


def failed_error_metadata_exists(run_id, root, launch):
    if launch.get("exists") and (launch.get("error") or launch.get("stderr") or launch.get("exit_code") not in {None, 0}):
        return True
    for event in reversed(read_events(run_id, root)):
        if event.get("event") != "status_marked_failed":
            continue
        payload = event.get("payload") or {}
        if payload.get("reason") or payload.get("message"):
            return True
    return False


def artifact_presence(run_id, artifact, root=Path.cwd()):
    path = run_path(run_id, root) / artifact
    return {
        "path": str(Path("runs") / validate_run_id(run_id) / artifact),
        "exists": path.exists(),
    }


def latest_launch_result(run_id, root=Path.cwd()):
    path = run_path(run_id, root) / "launch.json"
    payload = {
        "path": str(Path("runs") / validate_run_id(run_id) / "launch.json"),
        "exists": False,
        "execution_mode": "",
        "exit_code": None,
        "intake_status": "",
        "launch_time": "",
        "finish_time": "",
        "command_text": "",
        "error": "",
        "stderr": "",
    }
    if not path.exists():
        return payload
    try:
        stored = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise DavyError(f"Could not read launch metadata: {path}") from error
    if not isinstance(stored, dict):
        raise DavyError(f"Launch metadata must be an object: {path}")
    payload.update({
        "exists": True,
        "execution_mode": str(stored.get("execution_mode") or ""),
        "exit_code": stored.get("exit_code"),
        "intake_status": str(stored.get("intake_status") or ""),
        "launch_time": str(stored.get("launch_time") or ""),
        "finish_time": str(stored.get("finish_time") or ""),
        "command_text": str(stored.get("command_text") or ""),
        "error": str(stored.get("error") or ""),
        "stderr": str(stored.get("stderr") or ""),
    })
    return payload


def next_expected_action(protocol, codex_output, next_chatgpt_artifact, launch, integrity=None):
    if integrity and integrity.get("errors"):
        return "Resolve relay integrity errors before advancing this run."
    status_value = protocol["current_status"]
    if protocol.get("requires_captain"):
        reason = protocol.get("captain_reason") or "Captain approval is required."
        return f"Captain approval required: {reason}"
    if status_value == "complete":
        return "No action; run is complete."
    if status_value == "failed":
        if launch.get("exists") and launch.get("exit_code") not in {None, 0}:
            return "Review the failed Codex launch, then rerun safely or mark needs_captain."
        return "Review the failed run, then rerun safely or mark needs_captain."
    if not codex_output["exists"]:
        return "Run launch-codex --execute or record-codex with a Codex output file."
    if not next_chatgpt_artifact["exists"]:
        return "Run next-chatgpt to prepare the ChatGPT review artifact."
    if status_value == "ready_for_chatgpt":
        return "Send next_chatgpt.md to ChatGPT for review."
    if status_value == "waiting_for_chatgpt":
        return "Wait for ChatGPT review, then create the next Codex prompt when ready."
    if status_value in {"ready_for_codex", "waiting_for_codex"}:
        return "Run next-codex, then launch-codex when the generated prompt is ready."
    return "Inspect transcript and protocol to determine the next safe action."


def format_relay_status_view(view):
    launch = view["last_launch"]
    lines = [
        "DAVY Relay Status",
        f"Run: {view['run_id']}",
        f"Status: {view['current_status']}",
        f"Protocol: {view['protocol_path']}",
        f"Codex output: {presence_label(view['codex_output'])}",
        f"Next ChatGPT: {presence_label(view['next_chatgpt'])}",
        "Last Codex launch:",
    ]
    if not launch["exists"]:
        lines.append(f"- none ({launch['path']})")
    else:
        lines.extend([
            f"- mode: {launch['execution_mode'] or 'unknown'}",
            f"- exit code: {launch['exit_code']}",
            f"- intake: {launch['intake_status'] or 'unknown'}",
            f"- finished: {launch['finish_time'] or '(not finished)'}",
        ])
        if launch.get("error"):
            lines.append(f"- error: {launch['error']}")
        elif launch.get("stderr"):
            lines.append(f"- stderr: {launch['stderr']}")
    integrity = view.get("integrity") or {"ok": True, "errors": [], "warnings": []}
    lines.append("Integrity:")
    if integrity.get("ok"):
        lines.append("- ok")
    else:
        for error in integrity.get("errors") or []:
            lines.append(f"- error {error.get('code', 'unknown')}: {error.get('message', '')} ({error.get('path', '')})")
        for warning in integrity.get("warnings") or []:
            lines.append(f"- warning {warning.get('code', 'unknown')}: {warning.get('message', '')} ({warning.get('path', '')})")
    lines.append(f"Next action: {view['next_expected_action']}")
    lines.append("Missing files:")
    if view["missing"]:
        lines.extend(f"- {artifact}" for artifact in view["missing"])
    else:
        lines.append("- none")
    return "\n".join(lines)


def presence_label(artifact):
    state = "present" if artifact["exists"] else "missing"
    return f"{state} ({artifact['path']})"


def next_codex_prompt(run_id, root=Path.cwd()):
    protocol = load_protocol(run_id, root)
    if protocol.get("requires_captain"):
        reason = protocol.get("captain_reason") or "Captain approval is required."
        raise DavyError(f"Captain approval required: {reason}")
    prompt = render_next_codex_prompt(protocol)
    path = run_path(run_id, root) / "next_codex_prompt.md"
    path.write_text(prompt)
    return path


def launch_codex(run_id, root=Path.cwd(), execute=False, now=None, runner=None):
    root = Path(root)
    run_id = validate_run_id(run_id)
    protocol_path = run_path(run_id, root) / "protocol.json"
    prompt_path = run_path(run_id, root) / "next_codex_prompt.md"
    if not protocol_path.exists():
        raise DavyError(f"Missing protocol.json for run: {run_id}")
    if not prompt_path.exists():
        raise DavyError(f"Missing next_codex_prompt.md for run: {run_id}")

    protocol = load_protocol(run_id, root)
    run = load_run(run_id, root)
    if protocol.get("requires_captain"):
        reason = protocol.get("captain_reason") or "Captain approval is required."
        raise DavyError(f"Captain approval required: {reason}")
    if run.status == "complete":
        raise DavyError(f"Run is complete and cannot be launched: {run_id}")
    if run.status == "failed":
        raise DavyError(f"Run failed and cannot be launched: {run_id}")

    prompt_text = required_text(prompt_path.read_text(), "Next Codex prompt")
    command = codex_launch_command(protocol, prompt_path)
    command_text = launch_command_text(command, run_id)
    started_at = timestamp(now)
    metadata = {
        "run_id": run_id,
        "execution_mode": "execute" if execute else "dry_run",
        "command": command,
        "command_text": command_text,
        "prompt_path": str(Path("runs") / run_id / "next_codex_prompt.md"),
        "launch_time": started_at,
        "finish_time": "",
        "exit_code": None,
        "stdout": "",
        "stderr": "",
        "error": "",
        "intake_status": "not_run",
    }

    append_event(root, run_id, "codex_launch_prepared", started_at, {"command": command_text, "execution_mode": metadata["execution_mode"]})
    if not execute:
        write_launch_metadata(root, run_id, metadata)
        return metadata

    append_event(root, run_id, "codex_launch_started", started_at, {"command": command_text})
    try:
        result = (runner or run_codex_command)(command, prompt_text)
        metadata["exit_code"] = int(getattr(result, "returncode", 0))
        metadata["stdout"] = str(getattr(result, "stdout", "") or "")
        metadata["stderr"] = str(getattr(result, "stderr", "") or "")
    except Exception as error:
        metadata["exit_code"] = -1
        metadata["error"] = str(error)
    metadata["finish_time"] = timestamp()
    if metadata["exit_code"] == 0 and metadata["stdout"].strip():
        import_codex_output(
            run_id,
            metadata["stdout"],
            root=root,
            source="launch stdout",
            now=metadata["finish_time"],
            event_name="codex_output_imported_from_launch",
        )
        metadata["intake_status"] = "imported"
    elif metadata["exit_code"] not in {0, None}:
        metadata["intake_status"] = "skipped_failed_launch"
        fail_reason = metadata["error"] or metadata["stderr"] or f"Codex exited with code {metadata['exit_code']}"
        mark_status(run_id, "failed", reason=fail_reason, root=root, now=metadata["finish_time"])
    else:
        metadata["intake_status"] = "no_stdout"
    write_launch_metadata(root, run_id, metadata)
    append_event(
        root,
        run_id,
        "codex_launch_finished",
        metadata["finish_time"],
        {"exit_code": metadata["exit_code"], "error": metadata["error"], "intake_status": metadata["intake_status"]},
    )
    return metadata


def run_codex_command(command, prompt_text):
    return subprocess.run(
        command,
        input=prompt_text,
        capture_output=True,
        text=True,
        timeout=None,
    )


def codex_launch_command(protocol, prompt_path):
    repository = protocol.get("repository") or "."
    return ["codex", "exec", "--cd", repository, "-"]


def shell_command(command):
    return " ".join(shlex.quote(str(part)) for part in command)


def launch_command_text(command, run_id):
    prompt_path = Path("runs") / validate_run_id(run_id) / "next_codex_prompt.md"
    return f"{shell_command(command)} < {shlex.quote(str(prompt_path))}"


def write_launch_metadata(root, run_id, metadata):
    path = run_path(run_id, root) / "launch.json"
    path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
    return path


def transcript_view(run_id, root=Path.cwd()):
    root = Path(root)
    run = load_run(run_id, root)
    return {
        "run_id": run.run_id,
        "status": run.status,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "artifacts": {
            "chatgpt_prompt": artifact_payload(run_id, "chatgpt_prompt.md", root),
            "codex_prompt": artifact_payload(run_id, "codex_prompt.md", root),
            "codex_output": artifact_payload(run_id, "codex_output.md", root, required=False),
            "next_chatgpt": artifact_payload(run_id, "next_chatgpt.md", root, required=False),
        },
        "transcript": list(run.transcript),
        "events": read_events(run_id, root),
    }


def protocol_view(run_id, root=Path.cwd()):
    return sync_protocol(run_id, root)


def sync_protocol(run_id, root=Path.cwd()):
    root = Path(root)
    protocol = build_protocol(run_id, root)
    write_protocol(protocol, run_id, root)
    return protocol


def build_protocol(run_id, root=Path.cwd()):
    root = Path(root)
    run = load_run(run_id, root)
    events = read_events(run_id, root)
    prompt = artifact_text(run_id, "chatgpt_prompt.md", root, required=False)
    codex_output = artifact_text(run_id, "codex_output.md", root, required=False)
    sections = parse_markdown_sections(codex_output)
    status_reason = latest_status_reason(events, run.status)
    return {
        "protocol_version": PROTOCOL_VERSION,
        "run_id": run.run_id,
        "objective": first_nonempty_line(prompt),
        "repository": str(Path(root).resolve()),
        "current_status": run.status,
        "completed_work": section_items(sections, "completed work", "summary") or ([codex_output] if codex_output and run.status == "complete" else []),
        "files_changed": section_items(sections, "files changed", "files created", "files created/changed"),
        "tests_run": section_items(sections, "tests run", "validation"),
        "validation": section_items(sections, "validation", "validation results"),
        "remaining_risks": section_items(sections, "remaining risks", "risks"),
        "next_recommended_task": section_text(sections, "recommended next task", "next recommended task", "recommended davy-002", "recommended davy-003", "recommended davy-004", "recommended davy-005"),
        "requires_captain": run.status == "needs_captain",
        "captain_reason": status_reason if run.status == "needs_captain" else "",
        "timestamps": {
            "created_at": run.created_at,
            "updated_at": run.updated_at,
            "last_event_at": events[-1].get("created_at", "") if events else "",
        },
    }


def write_protocol(protocol, run_id, root=Path.cwd()):
    path = run_path(run_id, root) / "protocol.json"
    path.write_text(json.dumps(protocol, indent=2, sort_keys=True) + "\n")
    return path


def load_protocol(run_id, root=Path.cwd()):
    path = run_path(run_id, root) / "protocol.json"
    if not path.exists():
        return sync_protocol(run_id, root)
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise DavyError(f"Could not read protocol: {path}") from error
    validate_protocol(payload)
    return payload


def validate_protocol(payload):
    required = {
        "protocol_version": str,
        "run_id": str,
        "objective": str,
        "repository": str,
        "current_status": str,
        "completed_work": list,
        "files_changed": list,
        "tests_run": list,
        "validation": list,
        "remaining_risks": list,
        "next_recommended_task": str,
        "requires_captain": bool,
        "captain_reason": str,
        "timestamps": dict,
    }
    if not isinstance(payload, dict):
        raise DavyError("Protocol must be an object.")
    for field_name, expected_type in required.items():
        if field_name not in payload:
            raise DavyError(f"Protocol missing field: {field_name}")
        if not isinstance(payload[field_name], expected_type):
            raise DavyError(f"Protocol field has wrong type: {field_name}")
    validate_run_id(payload["run_id"])
    validate_status(payload["current_status"])
    for field_name in ("created_at", "updated_at", "last_event_at"):
        if field_name not in payload["timestamps"]:
            raise DavyError(f"Protocol timestamps missing field: {field_name}")
    return payload


def mark_status(run_id, next_status, reason="", root=Path.cwd(), now=None):
    next_status = validate_status(next_status)
    if next_status not in {"needs_captain", "complete", "failed"}:
        raise DavyError(f"Captain status is not supported: {next_status}")
    run = load_run(run_id, root)
    current_time = timestamp(now)
    updated = replace_run(run, status=next_status, updated_at=current_time)
    write_state(updated, root)
    append_event(
        root,
        run_id,
        f"status_marked_{next_status}",
        current_time,
        {"status": next_status, "reason": str(reason or "")},
    )
    sync_protocol(run_id, root)
    return updated


def list_runs(root=Path.cwd()):
    root = Path(root)
    runs_dir = root / RUNS_DIR
    if not runs_dir.is_dir():
        return []
    runs = []
    for state_path in sorted(runs_dir.glob("*/state.json")):
        try:
            runs.append(read_state(state_path))
        except DavyError:
            continue
    return sorted(runs, key=lambda run: (run.created_at, run.run_id))


def load_run(run_id, root=Path.cwd()):
    state_path = run_path(validate_run_id(run_id), root) / "state.json"
    if not state_path.exists():
        raise DavyError(f"Run not found: {run_id}")
    return read_state(state_path)


def read_state(path):
    try:
        payload = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise DavyError(f"Could not read state: {path}") from error
    for field_name in ("run_id", "status", "created_at", "updated_at", "transcript"):
        if field_name not in payload:
            raise DavyError(f"State missing field: {field_name}")
    validate_run_id(payload["run_id"])
    validate_status(payload["status"])
    if not isinstance(payload["transcript"], list):
        raise DavyError("Transcript must be a list.")
    return RelayRun(
        run_id=str(payload["run_id"]),
        status=str(payload["status"]),
        created_at=str(payload["created_at"]),
        updated_at=str(payload["updated_at"]),
        transcript=list(payload["transcript"]),
    )


def write_state(run, root=Path.cwd()):
    path = run_path(run.run_id, root) / "state.json"
    path.write_text(json.dumps(run.to_dict(), indent=2) + "\n")
    return path


def append_event(root, run_id, event, created_at, payload=None):
    path = run_path(run_id, root) / "events.jsonl"
    record = {
        "event": event,
        "created_at": created_at,
        "payload": payload or {},
    }
    with path.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def read_events(run_id, root=Path.cwd()):
    path = run_path(run_id, root) / "events.jsonl"
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise DavyError(f"Could not read event trail: {path}") from error
        if isinstance(event, dict):
            events.append(event)
    return events


def artifact_payload(run_id, artifact, root=Path.cwd(), required=True):
    path = run_path(run_id, root) / artifact
    if not path.exists():
        if required:
            raise DavyError(f"Missing artifact: {artifact}")
        return {"path": str(Path("runs") / validate_run_id(run_id) / artifact), "content": ""}
    return {
        "path": str(Path("runs") / validate_run_id(run_id) / artifact),
        "content": path.read_text().strip(),
    }


def artifact_text(run_id, artifact, root=Path.cwd(), required=True):
    path = run_path(run_id, root) / artifact
    if not path.exists():
        if required:
            raise DavyError(f"Missing artifact: {artifact}")
        return ""
    return path.read_text().strip()


def render_codex_prompt(run_id, chatgpt_prompt):
    return "\n".join([
        f"# DAVY Codex Prompt: {run_id}",
        "",
        "You are Codex, the implementation engineer.",
        "Bobby is the captain and approval gate. Do not commit, push, delete, install, use network services, or perform unsafe automation unless explicitly approved.",
        "Work from the ChatGPT plan below and write durable output that can be returned to ChatGPT for review.",
        "",
        "## ChatGPT Prompt",
        chatgpt_prompt.strip(),
        "",
    ])


def render_next_codex_prompt(protocol):
    return "\n".join([
        EXECUTION_POLICY,
        "",
        "# DAVY Next Codex Prompt",
        "",
        f"Run ID: {protocol['run_id']}",
        f"Repository: {protocol['repository']}",
        f"Current Status: {protocol['current_status']}",
        "",
        "## Objective",
        protocol.get("objective") or "No objective recorded.",
        "",
        "## Completed Work",
        bullet_lines(protocol.get("completed_work") or []),
        "",
        "## Files Changed",
        bullet_lines(protocol.get("files_changed") or []),
        "",
        "## Tests Run",
        bullet_lines(protocol.get("tests_run") or []),
        "",
        "## Validation",
        bullet_lines(protocol.get("validation") or []),
        "",
        "## Remaining Risks",
        bullet_lines(protocol.get("remaining_risks") or []),
        "",
        "## Next Recommended Task",
        protocol.get("next_recommended_task") or "Determine the next smallest safe DAVY task from repository state.",
        "",
        "## Instructions",
        "Implement the next smallest safe change for DAVY using the repository as source of truth.",
        "Preserve existing behavior, add focused tests, run the test suite, and write a handoff report.",
        "Do not commit unless explicitly instructed.",
        "",
    ])


def bullet_lines(items):
    if not items:
        return "- none"
    return "\n".join(f"- {item}" for item in items)


def render_next_chatgpt(run_id, chatgpt_prompt, codex_output):
    return "\n".join([
        f"# DAVY ChatGPT Review: {run_id}",
        "",
        "Bobby is the captain and approval gate. Review the Codex output below and decide the next instruction.",
        "DAVY has not sent anything automatically.",
        "",
        "## Original ChatGPT Prompt",
        chatgpt_prompt.strip(),
        "",
        "## Codex Output",
        codex_output.strip() or "No Codex output has been recorded yet.",
        "",
    ])


def parse_markdown_sections(text):
    sections = {}
    current = ""
    lines = []
    for line in str(text or "").splitlines():
        if line.startswith("#"):
            if current:
                sections[normalized_heading(current)] = "\n".join(lines).strip()
            current = line.lstrip("#").strip()
            lines = []
        else:
            lines.append(line)
    if current:
        sections[normalized_heading(current)] = "\n".join(lines).strip()
    return sections


def normalized_heading(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def section_items(sections, *names):
    value = section_text(sections, *names)
    if not value:
        return []
    items = []
    for line in value.splitlines():
        clean = line.strip()
        if not clean:
            continue
        if clean.startswith("-"):
            clean = clean[1:].strip()
        items.append(clean)
    return items


def section_text(sections, *names):
    for name in names:
        value = sections.get(normalized_heading(name), "").strip()
        if value:
            return value
    return ""


def first_nonempty_line(value):
    for line in str(value or "").splitlines():
        clean = line.strip()
        if clean:
            return clean
    return ""


def latest_status_reason(events, status_value):
    target = f"status_marked_{status_value}"
    for event in reversed(events):
        if event.get("event") != target:
            continue
        payload = event.get("payload") or {}
        return str(payload.get("reason") or payload.get("message") or "")
    return ""


def replace_run(run, **changes):
    payload = run.to_dict()
    payload.update(changes)
    return RelayRun(**payload)


def run_path(run_id, root=Path.cwd()):
    return Path(root) / RUNS_DIR / validate_run_id(run_id)


def resolve_existing_file(path, root):
    path = Path(path or "")
    if not path:
        raise DavyError("File path is required.")
    if not path.is_absolute():
        path = Path(root) / path
    if not path.exists() or not path.is_file():
        raise DavyError(f"File not found: {path}")
    return path


def validate_run_id(run_id):
    text = required_text(run_id, "Run ID")
    if not RUN_ID_PATTERN.fullmatch(text):
        raise DavyError(f"Invalid run id: {text}")
    return text


def validate_status(value):
    status_value = required_text(value, "Status")
    if status_value not in VALID_STATUSES:
        raise DavyError(f"Invalid status: {status_value}")
    return status_value


def required_text(value, label):
    text = str(value or "").strip()
    if not text:
        raise DavyError(f"{label} is required.")
    return text


def generated_run_id(now=None):
    return "davy-" + timestamp(now).replace("-", "").replace(":", "").replace(".", "")


def timestamp(now=None):
    if isinstance(now, str):
        return now
    return (now or datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")


def display_path(path, root):
    path = Path(path)
    root = Path(root)
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


def format_transcript_view(view):
    artifacts = view["artifacts"]
    lines = [
        "DAVY Transcript",
        f"Run: {view['run_id']}",
        f"Status: {view['status']}",
        f"Created: {view['created_at']}",
        f"Updated: {view['updated_at']}",
        "",
        "Original ChatGPT Prompt",
        artifacts["chatgpt_prompt"]["content"] or "(missing)",
        "",
        "Codex Prompt Artifact",
        f"Path: {artifacts['codex_prompt']['path']}",
        artifacts["codex_prompt"]["content"] or "(missing)",
        "",
        "Latest Codex Output",
        artifact_or_none(artifacts["codex_output"]),
        "",
        "Next ChatGPT Review",
        artifact_or_none(artifacts["next_chatgpt"]),
        "",
        "Event Trail",
    ]
    events = view.get("events") or []
    if not events:
        lines.append("- none")
    else:
        lines.extend(format_event(event) for event in events)
    return "\n".join(lines)


def artifact_or_none(artifact):
    if artifact.get("content"):
        return "\n".join([f"Path: {artifact['path']}", artifact["content"]])
    return f"Path: {artifact['path']}\n(none recorded)"


def format_event(event):
    payload = event.get("payload") or {}
    details = []
    reason = payload.get("reason")
    message = payload.get("message")
    status_value = payload.get("status")
    if status_value:
        details.append(f"status={status_value}")
    if reason:
        details.append(f"reason={reason}")
    if message:
        details.append(f"message={message}")
    suffix = f" ({'; '.join(details)})" if details else ""
    return f"- {event.get('created_at', 'unknown')}: {event.get('event', 'unknown')}{suffix}"
