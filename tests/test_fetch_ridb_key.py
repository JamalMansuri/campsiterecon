"""deploy/fetch_ridb_key.sh against a stub `op` and a fake RIDB — no network, no 1Password."""

import os
import stat
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "deploy" / "fetch_ridb_key.sh"

STUB_OP = """#!/bin/bash
# stub 1Password CLI: `op read <ref>`
case "$2" in
  *hang*)  exec sleep 300 ;;
  *good*)  echo "good-key" ;;
  *bad*)   echo "bad-key" ;;
  *empty*) ;;
esac
"""


class FakeRidb(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.headers.get("apikey") == "good-key" else 401)
        self.end_headers()

    def log_message(self, *args):
        pass


@pytest.fixture
def env(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), FakeRidb)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    op = tmp_path / "op"
    op.write_text(STUB_OP)
    op.chmod(0o755)
    yield dict(os.environ, OP_BIN=str(op), OP_SERVICE_ACCOUNT_TOKEN="stub", OP_TIMEOUT="2",
               CAMPSITESCOUT_KEY_FILE=str(tmp_path / "cfg" / "ridb_api_key"),
               RIDB_CHECK_URL=f"http://127.0.0.1:{server.server_port}/facilities/233359")
    server.shutdown()


def run(env, *args, refs=None):
    e = dict(env, OP_REFS=refs) if refs else env
    return subprocess.run(["bash", str(SCRIPT), *args], env=e, capture_output=True, text=True, timeout=60)


def test_falls_through_to_the_item_ridb_accepts_and_never_prints_the_key(env):
    out = run(env, refs="op://v/empty/credential op://v/bad/credential op://v/good/credential")
    assert out.returncode == 0, out.stderr
    key_file = Path(env["CAMPSITESCOUT_KEY_FILE"])
    assert key_file.read_text() == "good-key"
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(key_file.parent.stat().st_mode) == 0o700
    assert "good-key" not in out.stdout + out.stderr and "bad-key" not in out.stdout + out.stderr
    assert "HTTP 401" in out.stderr                      # the rejected item is explained, by name only


def test_no_acceptable_item_leaves_no_cache(env):
    out = run(env, refs="op://v/bad/credential")
    assert out.returncode == 1
    assert not Path(env["CAMPSITESCOUT_KEY_FILE"]).exists()


def test_hung_op_is_killed_by_the_watchdog(env):
    start = time.monotonic()
    out = run(env, refs="op://v/hang/credential op://v/good/credential")
    assert out.returncode == 3                           # a hang aborts; it does not spawn more op processes
    assert time.monotonic() - start < 20
    assert "hung" in out.stderr
    assert not Path(env["CAMPSITESCOUT_KEY_FILE"]).exists()


def test_check_mode(env):
    key_file = Path(env["CAMPSITESCOUT_KEY_FILE"])
    assert run(env, "--check").returncode == 1           # no cache yet
    key_file.parent.mkdir(parents=True)
    key_file.write_text("good-key\n")
    assert run(env, "--check").returncode == 0
    key_file.write_text("revoked-key")
    assert run(env, "--check").returncode == 1


def test_missing_service_account_token_is_a_clear_error(env):
    e = {k: v for k, v in env.items() if k != "OP_SERVICE_ACCOUNT_TOKEN"}
    e["OP_ENV_HELPER"] = "/nonexistent/.1password.sh"
    out = subprocess.run(["bash", str(SCRIPT)], env=e, capture_output=True, text=True, timeout=30)
    assert out.returncode == 2 and "OP_SERVICE_ACCOUNT_TOKEN" in out.stderr
