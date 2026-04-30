#!/usr/bin/env python3
"""Tests for state-manager.py core commands.

Run: python3 tests/test_state_manager.py
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import subprocess

STATE_MANAGER = Path(__file__).parent.parent / "scripts" / "state-manager.py"


def run_state_manager(*args, cwd=None):
    """Run state-manager.py and return (returncode, stdout, stderr)."""
    result = subprocess.run(
        [sys.executable, str(STATE_MANAGER)] + list(args),
        capture_output=True, text=True, cwd=cwd
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


class TestInitOverwriteProtection(unittest.TestCase):
    """P0 test: init must refuse to clobber active workspace."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cwd = self.tmpdir.name

    def tearDown(self):
        self.tmpdir.cleanup()

    def _init_state(self, task_name="test-task", extra_args=None):
        args = ["init", task_name]
        if extra_args:
            args.extend(extra_args)
        return run_state_manager(*args, cwd=self.cwd)

    def test_init_creates_state_file(self):
        rc, stdout, stderr = self._init_state()
        self.assertEqual(rc, 0, f"stderr: {stderr}")
        self.assertTrue(
            (Path(self.cwd) / ".claude" / "harness-state.json").exists()
        )

    def test_init_refuses_overwrite_active_workspace(self):
        # First init succeeds
        rc, _, _ = self._init_state("active-task")
        self.assertEqual(rc, 0)

        # Second init without --force must fail
        rc, stdout, stderr = self._init_state("second-task")
        self.assertNotEqual(rc, 0)
        self.assertIn("Active workspace exists", stderr)

    def test_init_force_overwrites(self):
        self._init_state("task1")
        rc, stdout, stderr = self._init_state("task2", ["--force"])
        self.assertEqual(rc, 0, f"stderr: {stderr}")

        state_path = Path(self.cwd) / ".claude" / "harness-state.json"
        state = json.loads(state_path.read_text())
        self.assertEqual(state["task_name"], "task2")

    def test_init_allows_overwrite_failed_workspace(self):
        self._init_state("task1")
        state_path = Path(self.cwd) / ".claude" / "harness-state.json"
        state = json.loads(state_path.read_text())
        state["status"] = "failed"
        state_path.write_text(json.dumps(state, indent=2) + "\n")

        rc, stdout, stderr = self._init_state("task2")
        self.assertEqual(rc, 0, f"stderr: {stderr}")

    def test_init_allows_overwrite_mission_complete(self):
        self._init_state("task1")
        state_path = Path(self.cwd) / ".claude" / "harness-state.json"
        state = json.loads(state_path.read_text())
        state["status"] = "mission_complete"
        state_path.write_text(json.dumps(state, indent=2) + "\n")

        rc, _, _ = self._init_state("task2")
        self.assertEqual(rc, 0)

    def test_init_flag_value_validation_rejects_flag_as_value(self):
        rc, stdout, stderr = run_state_manager(
            "init", "task", "--mode", "--verify", cwd=self.cwd
        )
        self.assertNotEqual(rc, 0)
        self.assertIn("flag-like", stderr.lower())


class TestStateMachineTransitions(unittest.TestCase):
    """Test critical state transitions: fail, reset-fail, trip-breaker."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cwd = self.tmpdir.name
        run_state_manager("init", "test-task", cwd=self.cwd)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _read_state(self):
        path = Path(self.cwd) / ".claude" / "harness-state.json"
        return json.loads(path.read_text())

    def _cmd(self, *args):
        return run_state_manager(*args, cwd=self.cwd)

    def test_read_returns_json(self):
        rc, stdout, _ = self._cmd("read")
        self.assertEqual(rc, 0)
        state = json.loads(stdout)
        self.assertEqual(state["status"], "idle")
        self.assertEqual(state["task_name"], "test-task")

    def test_update_modifies_field(self):
        self._cmd("update", "status", "running")
        state = self._read_state()
        self.assertEqual(state["status"], "running")

    def test_fail_increments_and_trips_breaker_at_3(self):
        self._cmd("fail")
        state = self._read_state()
        self.assertEqual(state["consecutive_failures"], 1)
        self.assertEqual(state["circuit_breaker"], "off")
        self.assertEqual(state["status"], "failed")

        self._cmd("fail")
        state = self._read_state()
        self.assertEqual(state["consecutive_failures"], 2)
        self.assertEqual(state["circuit_breaker"], "off")

        self._cmd("fail")
        state = self._read_state()
        self.assertEqual(state["consecutive_failures"], 3)
        self.assertEqual(state["circuit_breaker"], "tripped")

    def test_reset_fail_clears_breaker(self):
        self._cmd("fail")
        self._cmd("fail")
        self._cmd("fail")
        self._cmd("reset-fail")
        state = self._read_state()
        self.assertEqual(state["consecutive_failures"], 0)
        self.assertEqual(state["circuit_breaker"], "off")

    def test_trip_breaker_sets_status_failed(self):
        """P0-1 fix: trip-breaker must also set status to failed."""
        self._cmd("trip-breaker")
        state = self._read_state()
        self.assertEqual(state["circuit_breaker"], "tripped")
        self.assertEqual(state["status"], "failed",
                         "trip-breaker must set status to 'failed' for stop-hook defense-in-depth")

    def test_step_advance_increments(self):
        state = self._read_state()
        self.assertEqual(state["current_step"], "Step 1")

        self._cmd("step-advance")
        state = self._read_state()
        self.assertEqual(state["current_step"], "Step 2")

        self._cmd("step-advance")
        state = self._read_state()
        self.assertEqual(state["current_step"], "Step 3")

    def test_atomic_write_no_tmp_remains(self):
        """P0-2 fix: verify no .tmp file remains after atomic write."""
        self._cmd("update", "status", "modified")

        state_path = Path(self.cwd) / ".claude" / "harness-state.json"
        state = json.loads(state_path.read_text())
        self.assertEqual(state["status"], "modified")

        tmp_path = state_path.with_suffix(".tmp")
        self.assertFalse(tmp_path.exists(),
                         f"Temporary file {tmp_path} should not exist after atomic write")

    def test_log_creates_execution_stream(self):
        self._cmd("log", "test log entry")
        log_path = Path(self.cwd) / ".claude" / "harness" / "logs" / "execution_stream.log"
        self.assertTrue(log_path.exists())
        content = log_path.read_text()
        self.assertIn("test log entry", content)

    def test_report_writes_structured_log(self):
        self._cmd("report", "subtask1", "strategy1", "verify1", "target1")
        log_path = Path(self.cwd) / ".claude" / "harness" / "logs" / "execution_stream.log"
        content = log_path.read_text()
        self.assertIn("Round Report", content)
        self.assertIn("subtask1", content)


class TestFindStateFileBoundary(unittest.TestCase):
    """P1-5 fix: find_state_file must respect project boundaries."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cwd = self.tmpdir.name

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_boundary_prevents_cross_project_search(self):
        """State in sibling project must NOT be found across boundaries."""
        # Create project-a with state and .git boundary
        proj_a = Path(self.cwd) / "project-a"
        (proj_a / ".claude").mkdir(parents=True)
        (proj_a / ".claude" / "harness-state.json").write_text(
            json.dumps({"status": "idle", "task_name": "project-a-task"}))
        (proj_a / ".git").mkdir()

        # Create project-b with its own .git boundary (no state)
        proj_b = Path(self.cwd) / "project-b"
        (proj_b / "src").mkdir(parents=True)
        (proj_b / ".git").mkdir()

        # Run from project-b/src/:
        #   project-b/src/.claude/harness-state.json -> no
        #   project-b/.git exists -> STOP
        # Should NOT find project-a's state
        rc, stdout, _ = run_state_manager("read", cwd=str(proj_b / "src"))
        self.assertNotEqual(rc, 0,
                            "Should fail because .git boundary prevents cross-project search")

    def test_state_found_from_subdirectory_without_boundary(self):
        """Without boundary marker, find_state_file should search up successfully."""
        state_dir = Path(self.cwd) / ".claude"
        state_dir.mkdir(parents=True)
        state_file = state_dir / "harness-state.json"
        state_file.write_text(json.dumps({"status": "idle", "task_name": "test"}))

        subdir = Path(self.cwd) / "sub" / "deep"
        subdir.mkdir(parents=True)

        rc, stdout, _ = run_state_manager("read", cwd=str(subdir))
        self.assertEqual(rc, 0)
        state = json.loads(stdout)
        self.assertEqual(state["task_name"], "test")


class TestCmdArchive(unittest.TestCase):
    """Test cmd_archive moves state to archive and removes original."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cwd = self.tmpdir.name
        run_state_manager("init", "archive-test", cwd=self.cwd)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _read_state(self):
        path = Path(self.cwd) / ".claude" / "harness-state.json"
        return json.loads(path.read_text())

    def test_archive_moves_state_file(self):
        state_path = Path(self.cwd) / ".claude" / "harness-state.json"
        self.assertTrue(state_path.exists(), "State file should exist after init")

        rc, stdout, _ = run_state_manager("archive", cwd=self.cwd)
        self.assertEqual(rc, 0, f"archive command failed: {stdout}")

        # Original state file should be gone
        self.assertFalse(state_path.exists(), "State file should be removed after archive")

        # Archive directory should exist and contain the state file
        archive_dir = Path(self.cwd) / ".claude/harness/archive"
        self.assertTrue(archive_dir.exists(), "Archive directory should exist")
        archived_files = list(archive_dir.rglob("harness-state.json"))
        self.assertTrue(len(archived_files) > 0, "Archived state file should exist in archive dir")


class TestCmdPhaseAdvance(unittest.TestCase):
    """Test cmd_phase_advance increments phase counter."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cwd = self.tmpdir.name

    def tearDown(self):
        self.tmpdir.cleanup()

    def _read_state(self):
        path = Path(self.cwd) / ".claude" / "harness-state.json"
        return json.loads(path.read_text())

    def _cmd(self, *args):
        return run_state_manager(*args, cwd=self.cwd)

    def test_phase_advance_increments_counter(self):
        # Initialize with a state that has current_phase set
        rc, _, _ = self._cmd("init", "phase-test")
        self.assertEqual(rc, 0)

        # Manually set current_phase and mark all steps as completed
        state_path = Path(self.cwd) / ".claude" / "harness-state.json"
        state = json.loads(state_path.read_text())
        state["current_phase"] = 1
        state["step_statuses"] = {"Step 1": "completed", "Step 2": "completed"}
        state_path.write_text(json.dumps(state, indent=2) + "\n")

        rc, stdout, stderr = self._cmd("phase-advance")
        self.assertEqual(rc, 0, f"phase-advance failed: {stderr}")
        self.assertIn("Phase 2", stdout)

        state = self._read_state()
        self.assertEqual(state["current_phase"], 2)
        # step_statuses should be reset after phase advance
        self.assertEqual(state["step_statuses"], {})


class TestCmdUpdateNegative(unittest.TestCase):
    """Test that cmd_update rejects keys not in SAFE_UPDATE_KEYS."""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.cwd = self.tmpdir.name
        run_state_manager("init", "update-test", cwd=self.cwd)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_update_rejects_unsafe_key(self):
        rc, stdout, stderr = run_state_manager(
            "update", "consecutive_failures", "999", cwd=self.cwd
        )
        self.assertNotEqual(rc, 0, "Should reject update of unsafe key")
        self.assertIn("not in allowlist", stderr)

    def test_update_rejects_unknown_key(self):
        rc, stdout, stderr = run_state_manager(
            "update", "totally_made_up_field", "value", cwd=self.cwd
        )
        self.assertNotEqual(rc, 0, "Should reject update of unknown key")
        self.assertIn("not in allowlist", stderr)

    def test_update_accepts_safe_key(self):
        rc, stdout, stderr = run_state_manager(
            "update", "status", "running", cwd=self.cwd
        )
        self.assertEqual(rc, 0, f"Should accept safe key: {stderr}")


if __name__ == "__main__":
    unittest.main()
