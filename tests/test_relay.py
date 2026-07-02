import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from davy.cli import main
from davy.relay import (
    DavyError,
    codex_prompt,
    create_run,
    launch_codex,
    list_runs,
    load_run,
    mark_status,
    next_chatgpt,
    next_codex_prompt,
    record_codex_output,
    protocol_view,
    transcript_view,
)


class RelayTests(unittest.TestCase):
    def test_create_run_persists_required_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("Build the smallest useful prototype.")

            run = create_run(prompt, root=root, run_id="davy-test", now=fixed_time())

            self.assertEqual(run.status, "ready_for_codex")
            run_dir = root / "runs" / "davy-test"
            self.assertTrue((run_dir / "state.json").exists())
            self.assertTrue((run_dir / "chatgpt_prompt.md").exists())
            self.assertTrue((run_dir / "codex_prompt.md").exists())
            self.assertTrue((run_dir / "events.jsonl").exists())
            self.assertIn("Build the smallest useful prototype.", (run_dir / "codex_prompt.md").read_text())
            self.assertEqual(len(run.transcript), 2)

    def test_run_survives_reload_from_state_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("Durable state please.")
            create_run(prompt, root=root, run_id="davy-reload", now=fixed_time())

            reloaded = load_run("davy-reload", root=root)

            self.assertEqual(reloaded.run_id, "davy-reload")
            self.assertEqual(reloaded.status, "ready_for_codex")
            self.assertEqual(reloaded.created_at, "2026-07-01T19:00:00Z")

    def test_codex_prompt_marks_waiting_for_codex(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("Send to Codex manually.")
            create_run(prompt, root=root, run_id="davy-codex")

            path = codex_prompt("davy-codex", root=root, now=fixed_time())

            self.assertEqual(path.name, "codex_prompt.md")
            self.assertEqual(load_run("davy-codex", root=root).status, "waiting_for_codex")

    def test_record_codex_output_and_generate_next_chatgpt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            output = root / "codex.md"
            prompt.write_text("Build relay.")
            output.write_text("Implemented relay files and tests.")
            create_run(prompt, root=root, run_id="davy-record", now=fixed_time())

            run = record_codex_output("davy-record", output, root=root, now=fixed_time())

            run_dir = root / "runs" / "davy-record"
            self.assertEqual(run.status, "ready_for_chatgpt")
            self.assertEqual((run_dir / "codex_output.md").read_text().strip(), "Implemented relay files and tests.")
            self.assertIn("Implemented relay files and tests.", (run_dir / "next_chatgpt.md").read_text())
            self.assertEqual(len(run.transcript), 4)

    def test_next_chatgpt_marks_waiting_for_chatgpt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            output = root / "codex.md"
            prompt.write_text("Build relay.")
            output.write_text("Done.")
            create_run(prompt, root=root, run_id="davy-chatgpt")
            record_codex_output("davy-chatgpt", output, root=root)

            path = next_chatgpt("davy-chatgpt", root=root, now=fixed_time())

            self.assertEqual(path.name, "next_chatgpt.md")
            self.assertEqual(load_run("davy-chatgpt", root=root).status, "waiting_for_chatgpt")

    def test_list_runs_returns_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.md"
            second = root / "second.md"
            first.write_text("First")
            second.write_text("Second")
            create_run(first, root=root, run_id="davy-first")
            create_run(second, root=root, run_id="davy-second")

            runs = list_runs(root=root)

            self.assertEqual([run.run_id for run in runs], ["davy-first", "davy-second"])
            self.assertEqual([run.status for run in runs], ["ready_for_codex", "ready_for_codex"])


    def test_mark_needs_captain_records_event_and_preserves_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("Need review")
            created = create_run(prompt, root=root, run_id="davy-captain", now=fixed_time())

            run = mark_status(
                "davy-captain",
                "needs_captain",
                reason="Approval needed",
                root=root,
                now=fixed_time(),
            )

            self.assertEqual(run.status, "needs_captain")
            self.assertEqual(run.transcript, created.transcript)
            events = event_records(root, "davy-captain")
            self.assertEqual(events[-1]["event"], "status_marked_needs_captain")
            self.assertEqual(events[-1]["payload"]["reason"], "Approval needed")
            self.assertEqual(load_run("davy-captain", root=root).status, "needs_captain")

    def test_mark_complete_records_event_and_list_reflects_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("Complete me")
            create_run(prompt, root=root, run_id="davy-complete")

            run = mark_status("davy-complete", "complete", reason="Reviewed", root=root, now=fixed_time())

            self.assertEqual(run.status, "complete")
            self.assertEqual(list_runs(root=root)[0].status, "complete")
            self.assertEqual(event_records(root, "davy-complete")[-1]["event"], "status_marked_complete")
            self.assertEqual(event_records(root, "davy-complete")[-1]["payload"]["reason"], "Reviewed")

    def test_mark_failed_records_event_and_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("Fail me")
            create_run(prompt, root=root, run_id="davy-failed")

            run = mark_status("davy-failed", "failed", reason="Tests failed", root=root, now=fixed_time())

            self.assertEqual(run.status, "failed")
            self.assertEqual(load_run("davy-failed", root=root).status, "failed")
            self.assertEqual(event_records(root, "davy-failed")[-1]["payload"]["reason"], "Tests failed")

    def test_cli_captain_complete_and_fail_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("CLI status")
            create_run(prompt, root=root, run_id="davy-cli-status")
            cwd = Path.cwd()
            try:
                import os
                os.chdir(root)
                main(["captain", "davy-cli-status", "--reason", "Need approval"])
                self.assertEqual(load_run("davy-cli-status", root=root).status, "needs_captain")
                main(["complete", "davy-cli-status", "--reason", "Accepted"])
                self.assertEqual(load_run("davy-cli-status", root=root).status, "complete")
                main(["fail", "davy-cli-status", "--reason", "Regression"])
                self.assertEqual(load_run("davy-cli-status", root=root).status, "failed")
            finally:
                os.chdir(cwd)


    def test_transcript_view_after_create_includes_prompt_and_codex_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("Transcript after create")
            create_run(prompt, root=root, run_id="davy-transcript-create", now=fixed_time())

            view = transcript_view("davy-transcript-create", root=root)

            self.assertEqual(view["run_id"], "davy-transcript-create")
            self.assertEqual(view["status"], "ready_for_codex")
            self.assertIn("Transcript after create", view["artifacts"]["chatgpt_prompt"]["content"])
            self.assertIn("DAVY Codex Prompt", view["artifacts"]["codex_prompt"]["content"])
            self.assertEqual(view["artifacts"]["codex_output"]["content"], "")
            self.assertEqual([event["event"] for event in view["events"]], ["created", "codex_prompt_prepared"])

    def test_transcript_view_after_record_codex_includes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            output = root / "codex.md"
            prompt.write_text("Transcript after output")
            output.write_text("Codex finished the work.")
            create_run(prompt, root=root, run_id="davy-transcript-output")
            record_codex_output("davy-transcript-output", output, root=root, now=fixed_time())

            view = transcript_view("davy-transcript-output", root=root)

            self.assertEqual(view["status"], "ready_for_chatgpt")
            self.assertEqual(view["artifacts"]["codex_output"]["content"], "Codex finished the work.")
            self.assertIn("Codex finished the work.", view["artifacts"]["next_chatgpt"]["content"])
            self.assertEqual(len(view["transcript"]), 4)

    def test_transcript_view_includes_captain_complete_fail_reason_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("Reason trail")
            create_run(prompt, root=root, run_id="davy-transcript-events")
            mark_status("davy-transcript-events", "needs_captain", reason="Need approval", root=root, now=fixed_time())
            mark_status("davy-transcript-events", "complete", reason="Accepted", root=root, now=fixed_time())
            mark_status("davy-transcript-events", "failed", reason="Regression", root=root, now=fixed_time())

            view = transcript_view("davy-transcript-events", root=root)
            reasons = [event.get("payload", {}).get("reason") for event in view["events"]]

            self.assertEqual(view["status"], "failed")
            self.assertIn("Need approval", reasons)
            self.assertIn("Accepted", reasons)
            self.assertIn("Regression", reasons)

    def test_cli_transcript_json_outputs_view(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("CLI transcript")
            create_run(prompt, root=root, run_id="davy-cli-transcript")
            cwd = Path.cwd()
            try:
                import contextlib
                import io
                import os
                os.chdir(root)
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    main(["transcript", "davy-cli-transcript", "--json"])
            finally:
                os.chdir(cwd)

            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload["run_id"], "davy-cli-transcript")
            self.assertIn("CLI transcript", payload["artifacts"]["chatgpt_prompt"]["content"])


    def test_create_run_persists_valid_protocol_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("Protocol objective")

            create_run(prompt, root=root, run_id="davy-protocol", now=fixed_time())

            protocol_path = root / "runs" / "davy-protocol" / "protocol.json"
            self.assertTrue(protocol_path.exists())
            payload = json.loads(protocol_path.read_text())
            assert_protocol_shape(self, payload)
            self.assertEqual(payload["protocol_version"], "1.0")
            self.assertEqual(payload["run_id"], "davy-protocol")
            self.assertEqual(payload["objective"], "Protocol objective")
            self.assertEqual(payload["current_status"], "ready_for_codex")
            self.assertFalse(payload["requires_captain"])

    def test_protocol_syncs_with_captain_status_and_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("Captain protocol")
            create_run(prompt, root=root, run_id="davy-protocol-captain")

            mark_status(
                "davy-protocol-captain",
                "needs_captain",
                reason="Needs approval",
                root=root,
                now=fixed_time(),
            )

            payload = protocol_view("davy-protocol-captain", root=root)
            assert_protocol_shape(self, payload)
            self.assertEqual(payload["current_status"], "needs_captain")
            self.assertTrue(payload["requires_captain"])
            self.assertEqual(payload["captain_reason"], "Needs approval")
            self.assertEqual(payload["timestamps"]["updated_at"], load_run("davy-protocol-captain", root=root).updated_at)

    def test_protocol_extracts_structured_codex_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            output = root / "codex.md"
            prompt.write_text("Structured protocol")
            output.write_text("""# Result

## Completed Work
- Built protocol

## Files Changed
- davy/relay.py

## Tests Run
- python3 -m unittest discover -s tests -q

## Validation
- Protocol JSON passed shape checks

## Remaining Risks
- Parser is lightweight

## Next Recommended Task
DAVY-005 Path helper
""")
            create_run(prompt, root=root, run_id="davy-protocol-sections")
            record_codex_output("davy-protocol-sections", output, root=root, now=fixed_time())

            payload = protocol_view("davy-protocol-sections", root=root)

            self.assertEqual(payload["completed_work"], ["Built protocol"])
            self.assertEqual(payload["files_changed"], ["davy/relay.py"])
            self.assertEqual(payload["tests_run"], ["python3 -m unittest discover -s tests -q"])
            self.assertEqual(payload["validation"], ["Protocol JSON passed shape checks"])
            self.assertEqual(payload["remaining_risks"], ["Parser is lightweight"])
            self.assertEqual(payload["next_recommended_task"], "DAVY-005 Path helper")

    def test_protocol_command_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("CLI protocol")
            create_run(prompt, root=root, run_id="davy-cli-protocol")
            cwd = Path.cwd()
            try:
                import contextlib
                import io
                import os
                os.chdir(root)
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    main(["protocol", "davy-cli-protocol"])
            finally:
                os.chdir(cwd)

            payload = json.loads(stdout.getvalue())
            assert_protocol_shape(self, payload)
            self.assertEqual(payload["run_id"], "davy-cli-protocol")
            self.assertEqual(payload["current_status"], "ready_for_codex")

    def test_protocol_view_backfills_existing_run_without_protocol_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("Legacy run")
            create_run(prompt, root=root, run_id="davy-legacy")
            protocol_path = root / "runs" / "davy-legacy" / "protocol.json"
            protocol_path.unlink()

            payload = protocol_view("davy-legacy", root=root)

            assert_protocol_shape(self, payload)
            self.assertTrue(protocol_path.exists())
            self.assertEqual(payload["objective"], "Legacy run")


    def test_next_codex_prompt_generates_artifact_from_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            output = root / "codex.md"
            prompt.write_text("Generate next prompt")
            output.write_text("""# Result

## Completed Work
- Added protocol

## Files Changed
- davy/relay.py

## Tests Run
- pytest

## Validation
- passed

## Remaining Risks
- lightweight parser

## Next Recommended Task
DAVY-006 Improve local handoff ergonomics
""")
            create_run(prompt, root=root, run_id="davy-next-codex")
            record_codex_output("davy-next-codex", output, root=root)

            path = next_codex_prompt("davy-next-codex", root=root)
            content = path.read_text()

            self.assertEqual(path.name, "next_codex_prompt.md")
            self.assertTrue(path.exists())
            self.assertIn("Execution Policy", content)
            self.assertIn("You do NOT have approval to:", content)
            self.assertIn("## Objective\nGenerate next prompt", content)
            self.assertIn("- Added protocol", content)
            self.assertIn("- davy/relay.py", content)
            self.assertIn("- pytest", content)
            self.assertIn("- passed", content)
            self.assertIn("- lightweight parser", content)
            self.assertIn("DAVY-006 Improve local handoff ergonomics", content)
            self.assertIn("Do not commit unless explicitly instructed.", content)

    def test_next_codex_refuses_when_captain_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("Captain required")
            create_run(prompt, root=root, run_id="davy-next-captain")
            mark_status("davy-next-captain", "needs_captain", reason="Bobby must approve", root=root)

            with self.assertRaisesRegex(DavyError, "Bobby must approve"):
                next_codex_prompt("davy-next-captain", root=root)

            self.assertFalse((root / "runs" / "davy-next-captain" / "next_codex_prompt.md").exists())

    def test_cli_next_codex_prints_prompt_and_writes_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("CLI next codex")
            create_run(prompt, root=root, run_id="davy-cli-next-codex")
            cwd = Path.cwd()
            try:
                import contextlib
                import io
                import os
                os.chdir(root)
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    main(["next-codex", "davy-cli-next-codex"])
            finally:
                os.chdir(cwd)

            output = stdout.getvalue()
            self.assertIn("Execution Policy", output)
            self.assertIn("CLI next codex", output)
            self.assertTrue((root / "runs" / "davy-cli-next-codex" / "next_codex_prompt.md").exists())


    def test_launch_codex_dry_run_prints_command_and_records_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_next_codex_run(root, "davy-launch-dry")

            metadata = launch_codex("davy-launch-dry", root=root, execute=False, now=fixed_time())

            self.assertEqual(metadata["execution_mode"], "dry_run")
            self.assertIn("codex exec", metadata["command_text"])
            self.assertIn("runs/davy-launch-dry/next_codex_prompt.md", metadata["command_text"])
            self.assertIsNone(metadata["exit_code"])
            launch_payload = json.loads((root / "runs" / "davy-launch-dry" / "launch.json").read_text())
            self.assertEqual(launch_payload["command_text"], metadata["command_text"])
            self.assertEqual(event_records(root, "davy-launch-dry")[-1]["event"], "codex_launch_prepared")

    def test_launch_codex_execute_records_finish_and_exit_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_next_codex_run(root, "davy-launch-exec")
            calls = []

            def runner(command, prompt_text):
                calls.append((command, prompt_text))
                return FakeProcessResult(returncode=0, stdout="ok", stderr="")

            metadata = launch_codex("davy-launch-exec", root=root, execute=True, now=fixed_time(), runner=runner)

            self.assertEqual(metadata["execution_mode"], "execute")
            self.assertEqual(metadata["exit_code"], 0)
            self.assertEqual(metadata["stdout"], "ok")
            self.assertEqual(calls[0][0][:2], ["codex", "exec"])
            self.assertIn("Execution Policy", calls[0][1])
            events = [event["event"] for event in event_records(root, "davy-launch-exec")]
            self.assertIn("codex_launch_started", events)
            self.assertIn("codex_launch_finished", events)

    def test_launch_codex_execute_records_runner_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_next_codex_run(root, "davy-launch-error")

            def runner(command, prompt_text):
                raise RuntimeError("codex unavailable")

            metadata = launch_codex("davy-launch-error", root=root, execute=True, runner=runner)

            self.assertEqual(metadata["exit_code"], -1)
            self.assertEqual(metadata["error"], "codex unavailable")
            self.assertEqual(event_records(root, "davy-launch-error")[-1]["payload"]["error"], "codex unavailable")

    def test_launch_codex_refuses_missing_protocol_or_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("Launch validation")
            create_run(prompt, root=root, run_id="davy-launch-missing")

            with self.assertRaisesRegex(DavyError, "Missing next_codex_prompt"):
                launch_codex("davy-launch-missing", root=root)

            next_codex_prompt("davy-launch-missing", root=root)
            (root / "runs" / "davy-launch-missing" / "protocol.json").unlink()
            with self.assertRaisesRegex(DavyError, "Missing protocol"):
                launch_codex("davy-launch-missing", root=root)

    def test_launch_codex_refuses_captain_complete_and_failed_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_next_codex_run(root, "davy-launch-captain")
            mark_status("davy-launch-captain", "needs_captain", reason="Need approval", root=root)
            with self.assertRaisesRegex(DavyError, "Need approval"):
                launch_codex("davy-launch-captain", root=root)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_next_codex_run(root, "davy-launch-complete")
            mark_status("davy-launch-complete", "complete", reason="Done", root=root)
            with self.assertRaisesRegex(DavyError, "complete"):
                launch_codex("davy-launch-complete", root=root)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_next_codex_run(root, "davy-launch-failed")
            mark_status("davy-launch-failed", "failed", reason="Bad", root=root)
            with self.assertRaisesRegex(DavyError, "failed"):
                launch_codex("davy-launch-failed", root=root)

    def test_cli_launch_codex_dry_run_outputs_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_next_codex_run(root, "davy-cli-launch")
            cwd = Path.cwd()
            try:
                import contextlib
                import io
                import os
                os.chdir(root)
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout):
                    main(["launch-codex", "davy-cli-launch"])
            finally:
                os.chdir(cwd)

            output = stdout.getvalue()
            self.assertIn("DAVY Codex Launch", output)
            self.assertIn("Mode: dry_run", output)
            self.assertIn("codex exec", output)
            self.assertTrue((root / "runs" / "davy-cli-launch" / "launch.json").exists())


    def test_successful_launch_imports_stdout_into_relay_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_next_codex_run(root, "davy-launch-intake")

            def runner(command, prompt_text):
                return FakeProcessResult(returncode=0, stdout="# Result\n\n## Completed Work\n- Imported from launch\n\n## Validation\n- stdout captured\n", stderr="")

            metadata = launch_codex("davy-launch-intake", root=root, execute=True, runner=runner)

            self.assertEqual(metadata["intake_status"], "imported")
            self.assertIn("Imported from launch", (root / "runs" / "davy-launch-intake" / "codex_output.md").read_text())
            self.assertIn("Imported from launch", (root / "runs" / "davy-launch-intake" / "next_chatgpt.md").read_text())
            self.assertEqual(load_run("davy-launch-intake", root=root).status, "ready_for_chatgpt")
            protocol = protocol_view("davy-launch-intake", root=root)
            self.assertEqual(protocol["completed_work"], ["Imported from launch"])
            events = [event["event"] for event in event_records(root, "davy-launch-intake")]
            self.assertIn("codex_output_imported_from_launch", events)
            self.assertIn("codex_launch_finished", events)

    def test_successful_launch_with_empty_stdout_does_not_clobber_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_next_codex_run(root, "davy-launch-empty")
            before = (root / "runs" / "davy-launch-empty" / "codex_output.md").read_text()

            def runner(command, prompt_text):
                return FakeProcessResult(returncode=0, stdout="", stderr="")

            metadata = launch_codex("davy-launch-empty", root=root, execute=True, runner=runner)

            self.assertEqual(metadata["intake_status"], "no_stdout")
            self.assertEqual((root / "runs" / "davy-launch-empty" / "codex_output.md").read_text(), before)
            self.assertEqual(load_run("davy-launch-empty", root=root).status, "ready_for_chatgpt")

    def test_failed_launch_does_not_clobber_prior_output_and_marks_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prepare_next_codex_run(root, "davy-launch-fail-intake")
            before = (root / "runs" / "davy-launch-fail-intake" / "codex_output.md").read_text()

            def runner(command, prompt_text):
                return FakeProcessResult(returncode=2, stdout="new output should not import", stderr="boom")

            metadata = launch_codex("davy-launch-fail-intake", root=root, execute=True, runner=runner)

            self.assertEqual(metadata["intake_status"], "skipped_failed_launch")
            self.assertEqual((root / "runs" / "davy-launch-fail-intake" / "codex_output.md").read_text(), before)
            self.assertEqual(load_run("davy-launch-fail-intake", root=root).status, "failed")
            protocol = protocol_view("davy-launch-fail-intake", root=root)
            self.assertEqual(protocol["current_status"], "failed")
            self.assertFalse(protocol["requires_captain"])
            self.assertIn("boom", event_records(root, "davy-launch-fail-intake")[-2]["payload"]["reason"])

    def test_manual_record_codex_still_overwrites_output_and_refreshes_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            first = root / "first.md"
            second = root / "second.md"
            prompt.write_text("Manual workflow")
            first.write_text("# Result\n\n## Completed Work\n- First output\n")
            second.write_text("# Result\n\n## Completed Work\n- Second output\n")
            create_run(prompt, root=root, run_id="davy-manual-record")
            record_codex_output("davy-manual-record", first, root=root)
            record_codex_output("davy-manual-record", second, root=root)

            self.assertIn("Second output", (root / "runs" / "davy-manual-record" / "codex_output.md").read_text())
            self.assertEqual(protocol_view("davy-manual-record", root=root)["completed_work"], ["Second output"])
            self.assertEqual(load_run("davy-manual-record", root=root).status, "ready_for_chatgpt")

    def test_invalid_run_id_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("No traversal")

            with self.assertRaisesRegex(DavyError, "Invalid run id"):
                create_run(prompt, root=root, run_id="../bad")

    def test_cli_create_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = root / "prompt.md"
            prompt.write_text("CLI prompt")
            cwd = Path.cwd()
            try:
                import os
                os.chdir(root)
                main(["create", "--prompt-file", "prompt.md", "--run-id", "davy-cli", "--json"])
            finally:
                os.chdir(cwd)

            state = json.loads((root / "runs" / "davy-cli" / "state.json").read_text())
            self.assertEqual(state["run_id"], "davy-cli")
            self.assertEqual(state["status"], "ready_for_codex")


def prepare_next_codex_run(root, run_id):
    prompt = Path(root) / "prompt.md"
    output = Path(root) / "codex.md"
    prompt.write_text("Launch objective")
    output.write_text("""# Result

## Completed Work
- Ready to launch

## Next Recommended Task
DAVY launch smoke
""")
    create_run(prompt, root=Path(root), run_id=run_id)
    record_codex_output(run_id, output, root=Path(root))
    return next_codex_prompt(run_id, root=Path(root))


class FakeProcessResult:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def assert_protocol_shape(testcase, payload):
    expected = {
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
    for field_name, expected_type in expected.items():
        testcase.assertIn(field_name, payload)
        testcase.assertIsInstance(payload[field_name], expected_type)
    for field_name in ("created_at", "updated_at", "last_event_at"):
        testcase.assertIn(field_name, payload["timestamps"])


def event_records(root, run_id):
    return [json.loads(line) for line in (Path(root) / "runs" / run_id / "events.jsonl").read_text().splitlines()]


def fixed_time():
    return datetime(2026, 7, 1, 19, 0, tzinfo=timezone.utc)


if __name__ == "__main__":
    unittest.main()
