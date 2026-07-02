import argparse
import json
from pathlib import Path

from davy.relay import (
    DavyError,
    codex_prompt,
    create_run,
    init_workspace,
    launch_codex,
    list_runs,
    mark_status,
    next_chatgpt,
    next_codex_prompt,
    record_codex_output,
    protocol_view,
    status,
    transcript_view,
    format_relay_status_view,
    format_transcript_view,
)


def build_parser():
    parser = argparse.ArgumentParser(prog="davy")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("init", help="Initialize DAVY local state")

    create = subparsers.add_parser("create", help="Create a relay run from a ChatGPT prompt file")
    create.add_argument("--prompt-file", required=True)
    create.add_argument("--run-id")
    create.add_argument("--json", action="store_true")

    codex = subparsers.add_parser("codex-prompt", help="Show the Codex prompt artifact")
    codex.add_argument("run_id")

    record = subparsers.add_parser("record-codex", help="Record Codex output from a file")
    record.add_argument("run_id")
    record.add_argument("--file", required=True)
    record.add_argument("--json", action="store_true")

    chatgpt = subparsers.add_parser("next-chatgpt", help="Show the next ChatGPT review artifact")
    chatgpt.add_argument("run_id")

    next_codex = subparsers.add_parser("next-codex", help="Generate the next Codex prompt from protocol state")
    next_codex.add_argument("run_id")

    launch_codex_parser = subparsers.add_parser("launch-codex", help="Prepare or execute a Codex launch from the next prompt")
    launch_codex_parser.add_argument("run_id")
    launch_codex_parser.add_argument("--execute", action="store_true")
    launch_codex_parser.add_argument("--json", action="store_true")

    inspect = subparsers.add_parser("status", help="Show one run status")
    inspect.add_argument("run_id")
    inspect.add_argument("--json", action="store_true")

    transcript = subparsers.add_parser("transcript", help="Show the full transcript and event trail")
    transcript.add_argument("run_id")
    transcript.add_argument("--json", action="store_true")

    protocol = subparsers.add_parser("protocol", help="Show deterministic protocol state")
    protocol.add_argument("run_id")

    list_parser = subparsers.add_parser("list", help="List relay runs")
    list_parser.add_argument("--json", action="store_true")

    captain = subparsers.add_parser("captain", help="Mark a run as needing captain input")
    captain.add_argument("run_id")
    captain.add_argument("--reason", default="")
    captain.add_argument("--json", action="store_true")

    complete = subparsers.add_parser("complete", help="Mark a run complete")
    complete.add_argument("run_id")
    complete.add_argument("--reason", default="")
    complete.add_argument("--json", action="store_true")

    fail = subparsers.add_parser("fail", help="Mark a run failed")
    fail.add_argument("run_id")
    fail.add_argument("--reason", default="")
    fail.add_argument("--json", action="store_true")

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    root = Path.cwd()

    try:
        if args.command == "init":
            path = init_workspace(root)
            print(f"Initialized DAVY: {path}")
            return
        if args.command == "create":
            run = create_run(args.prompt_file, root=root, run_id=args.run_id)
            print(json.dumps(run.to_dict(), indent=2) if args.json else format_run(run))
            return
        if args.command == "codex-prompt":
            path = codex_prompt(args.run_id, root=root)
            print(path.read_text())
            return
        if args.command == "record-codex":
            run = record_codex_output(args.run_id, args.file, root=root)
            print(json.dumps(run.to_dict(), indent=2) if args.json else format_run(run))
            return
        if args.command == "next-chatgpt":
            path = next_chatgpt(args.run_id, root=root)
            print(path.read_text())
            return
        if args.command == "next-codex":
            path = next_codex_prompt(args.run_id, root=root)
            print(path.read_text())
            return
        if args.command == "launch-codex":
            metadata = launch_codex(args.run_id, root=root, execute=args.execute)
            if args.json:
                print(json.dumps(metadata, indent=2))
            else:
                print(format_launch(metadata))
            return
        if args.command == "status":
            view = status(args.run_id, root=root)
            print(json.dumps(view, indent=2) if args.json else format_relay_status_view(view))
            return
        if args.command == "transcript":
            view = transcript_view(args.run_id, root=root)
            print(json.dumps(view, indent=2) if args.json else format_transcript_view(view))
            return
        if args.command == "protocol":
            print(json.dumps(protocol_view(args.run_id, root=root), indent=2))
            return
        if args.command == "list":
            runs = list_runs(root=root)
            if args.json:
                print(json.dumps([run.to_dict() for run in runs], indent=2))
            else:
                print(format_run_list(runs))
            return
        if args.command == "captain":
            run = mark_status(args.run_id, "needs_captain", reason=args.reason, root=root)
            print(json.dumps(run.to_dict(), indent=2) if args.json else format_run(run))
            return
        if args.command == "complete":
            run = mark_status(args.run_id, "complete", reason=args.reason, root=root)
            print(json.dumps(run.to_dict(), indent=2) if args.json else format_run(run))
            return
        if args.command == "fail":
            run = mark_status(args.run_id, "failed", reason=args.reason, root=root)
            print(json.dumps(run.to_dict(), indent=2) if args.json else format_run(run))
            return
    except DavyError as error:
        parser.exit(1, f"error: {error}\n")

    parser.print_help()


def format_run(run):
    return "\n".join([
        "DAVY Relay Run",
        f"Run: {run.run_id}",
        f"Status: {run.status}",
        f"Created: {run.created_at}",
        f"Updated: {run.updated_at}",
        f"Transcript entries: {len(run.transcript)}",
    ])


def format_run_list(runs):
    if not runs:
        return "DAVY Relay Runs\n- none"
    lines = ["DAVY Relay Runs"]
    for run in runs:
        lines.append(f"- {run.run_id}: {run.status} ({run.updated_at})")
    return "\n".join(lines)


def format_launch(metadata):
    lines = [
        "DAVY Codex Launch",
        f"Run: {metadata['run_id']}",
        f"Mode: {metadata['execution_mode']}",
        f"Command: {metadata['command_text']}",
        f"Prompt: {metadata['prompt_path']}",
    ]
    if metadata.get("finish_time"):
        lines.extend([
            f"Exit code: {metadata.get('exit_code')}",
            f"Finished: {metadata.get('finish_time')}",
        ])
        if metadata.get("error"):
            lines.append(f"Error: {metadata['error']}")
    return "\n".join(lines)
