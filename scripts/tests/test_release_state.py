"""Exercise orchestration failures without SSH, Docker, or a production DB.

Actual app/DB checks live in backend/tests/integration. These tests verify that
shell scripts stop at the right phase and choose the right rollback image.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


V1, V2, V3 = "1" * 40, "2" * 40, "3" * 40
SCRIPTS = Path(__file__).resolve().parents[1]

FAKE_TOOL = r'''#!/usr/bin/env python3
import json, os, pathlib, subprocess, sys
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ["CALL_LOG"], "a") as log:
    log.write(tool + " " + " ".join(args) + "\n")
phase = os.getenv("FAIL_PHASE", "")
joined = " ".join(args)
if tool == "sleep":
    sys.exit(0)
if tool == "curl":
    if args[-1].endswith("/api/health"):
        if phase == "health": sys.exit(22)
        print('{"status":"ok"}')
    elif args[-1].endswith("/api/version"):
        print(json.dumps({"version": os.environ["EXPECTED_VERSION"]}))
    else:
        print("200")
        sys.exit(0)
    if "--write-out" in args:
        print("201" if phase == "health_status" else "200")
    sys.exit(0)
if "pg_dump" in args:
    if phase == "backup": sys.exit(1)
    print("fake dump")
elif "pg_restore" in args:
    sys.stdin.read()
elif "pull" in args and phase == "pull":
    sys.exit(1)
elif "alembic upgrade head" in joined and phase == "migration":
    sys.exit(1)
elif "up" in args and "frontend" in args and phase == "up":
    sys.exit(1)
elif "app.smoke" in args:
    if phase == "smoke": sys.exit(1)
elif "python" in args and "-c" in args:
    sys.exit(subprocess.run([sys.executable, *args[args.index("-c"):]]).returncode)
'''


class ReleaseStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(SCRIPTS, self.root / "scripts")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for name in ("docker", "curl", "sleep"):
            script = self.bin / name
            script.write_text(FAKE_TOOL)
            script.chmod(0o755)
        (self.root / ".env.prod").write_text(
            "POSTGRES_USER=unit_test\nPOSTGRES_DB=unit_test\nPOSTGRES_PASSWORD=unit_test\n"
        )
        self.calls = self.root / "calls.log"
        self.env = {
            **os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
            "DEPLOY_DIR": str(self.root), "ENV_FILE": str(self.root / ".env.prod"),
            "CALL_LOG": str(self.calls), "HEALTH_ATTEMPTS": "2", "HEALTH_DELAY": "0",
        }

    def state(self):
        file = self.root / "state/versions.env"
        return dict(line.split("=", 1) for line in file.read_text().splitlines())

    def seed(self):
        folder = self.root / "state"
        folder.mkdir()
        (folder / "versions.env").write_text(
            f"CURRENT_VERSION={V2}\nPREVIOUS_VERSION={V1}\nLAST_SUCCESSFUL_VERSION={V2}\n"
        )

    def run_script(self, name, version=None, fail="", expected=None):
        args = ["bash", str(self.root / "scripts" / name)]
        if version is not None:
            args.append(version)
        return subprocess.run(
            args, env={**self.env, "FAIL_PHASE": fail, "EXPECTED_VERSION": expected or version or V2},
            capture_output=True, text=True,
        )

    def test_success_order_and_state(self):
        self.seed()
        result = self.run_script("deploy.sh", V3)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        log = self.calls.read_text()
        phases = ["pg_dump", "pull backend frontend", "alembic upgrade head",
                  "up -d --no-build --no-deps backend frontend", "/api/health", "app.smoke"]
        positions = [log.index(phase) for phase in phases]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(self.state(), {
            "CURRENT_VERSION": V3, "PREVIOUS_VERSION": V2, "LAST_SUCCESSFUL_VERSION": V3,
        })
        self.assertEqual(len(list((self.root / "backups").glob("*.dump"))), 1)

    def test_migration_failure_keeps_old_state_and_does_not_start_candidate(self):
        self.seed()
        result = self.run_script("deploy.sh", V3, fail="migration")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.state()["CURRENT_VERSION"], V2)
        self.assertNotIn("up -d --no-build", self.calls.read_text())

    def test_backup_failure_stops_before_pull(self):
        self.seed()
        result = self.run_script("deploy.sh", V3, fail="backup")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("pull backend frontend", self.calls.read_text())
        self.assertEqual(list((self.root / "backups").glob("*")), [])

    def test_health_failure_rolls_back_to_last_success_not_older_previous(self):
        self.seed()
        self.assertNotEqual(self.run_script("deploy.sh", V3, fail="health").returncode, 0)
        self.assertEqual(self.state()["CURRENT_VERSION"], V3)
        self.assertEqual(self.state()["LAST_SUCCESSFUL_VERSION"], V2)
        result = self.run_script("rollback.sh", expected=V2)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.state()["CURRENT_VERSION"], V2)
        self.assertEqual(self.state()["PREVIOUS_VERSION"], "")

    def test_retry_of_failed_candidate_preserves_recovery_version(self):
        self.seed()
        for _ in range(2):
            result = self.run_script("deploy.sh", V3, fail="smoke")
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(self.state()["PREVIOUS_VERSION"], V2)
            self.assertEqual(self.state()["LAST_SUCCESSFUL_VERSION"], V2)

    def test_health_requires_exact_http_200(self):
        self.seed()
        result = self.run_script("deploy.sh", V3, fail="health_status")
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("app.smoke", self.calls.read_text())
        self.assertEqual(self.state()["LAST_SUCCESSFUL_VERSION"], V2)

    def test_healthy_release_rollback_uses_previous_image_without_migration(self):
        self.seed()
        result = self.run_script("rollback.sh", expected=V1)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.state()["CURRENT_VERSION"], V1)
        self.assertNotIn("alembic", self.calls.read_text())

    def test_first_failed_deployment_has_no_automatic_rollback(self):
        result = self.run_script("deploy.sh", V1, fail="smoke")
        self.assertNotEqual(result.returncode, 0)
        result = self.run_script("rollback.sh")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("No previous successful image", result.stderr)

    def test_invalid_sha_is_rejected(self):
        result = self.run_script("deploy.sh", "latest")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.calls.exists())


if __name__ == "__main__":
    unittest.main()
