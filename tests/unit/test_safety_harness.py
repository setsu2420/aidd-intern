import pytest
from pathlib import Path
from agent.tools.local_tools import (
    _bash_handler,
    _read_handler,
    _write_handler,
    _edit_handler,
    _check_path_safety,
    _files_read,
)


@pytest.mark.asyncio
async def test_bash_handler_blocks_dangerous_commands():
    # Attempt to recursively force-delete root
    res_root, ok_root = await _bash_handler({"command": "rm -rf /"})
    assert not ok_root
    assert "Execution blocked" in res_root
    assert "dangerous command" in res_root

    # Attempt recursive force-delete of home directory
    res_home, ok_home = await _bash_handler({"command": "rm -rf ~"})
    assert not ok_home
    assert "Execution blocked" in res_home

    # Safe command should be allowed (mock subprocess if needed or run a harmless echo)
    res_safe, ok_safe = await _bash_handler({"command": "echo 'safe command'"})
    # Since echo is harmless, it should succeed
    assert ok_safe
    assert "safe command" in res_safe.strip()


def test_path_safety_logic():
    # Outside allowed workspace and tmp
    safe, err = _check_path_safety("/etc/passwd")
    assert not safe
    assert "Permission denied" in err

    safe, err = _check_path_safety("/home/some_other_user/secret.key")
    assert not safe
    assert "Permission denied" in err

    # Strictly inside workspace
    safe, err = _check_path_safety("/home/xxue/aidd-intern/agent/core/session.py")
    assert safe
    assert err == ""

    # Strictly inside /tmp
    safe, err = _check_path_safety("/tmp/harmless_test_file.txt")
    assert safe
    assert err == ""


@pytest.mark.asyncio
async def test_filesystem_handlers_block_outside_paths():
    # Attempt to read out of bounds
    res_read, ok_read = await _read_handler({"path": "/etc/passwd"})
    assert not ok_read
    assert "Permission denied" in res_read

    # Attempt to write out of bounds
    res_write, ok_write = await _write_handler(
        {"path": "/etc/arbitrary_write", "content": "malicious"}
    )
    assert not ok_write
    assert "Permission denied" in res_write

    # Attempt to edit out of bounds
    res_edit, ok_edit = await _edit_handler(
        {
            "path": "/etc/passwd",
            "old_str": "root",
            "new_str": "hacked",
        }
    )
    assert not ok_edit
    assert "Permission denied" in res_edit


@pytest.mark.asyncio
async def test_filesystem_handlers_allow_workspace_paths(tmp_path):
    # Use workspace folder for simulated file operations
    # Create a test file inside workspace root
    workspace_test_file = Path(
        "/home/xxue/aidd-intern/temp_test_safety_harness_file.txt"
    )

    try:
        # We must bypass the read-before-write constraint initially or read a dummy
        # Clean up files read cache for test isolation
        _files_read.clear()

        # Test write (which resolves path safety)
        # Note: write fails if existing and not read. Here we create a new file.
        # But if it exists, it needs read. So we do _files_read.add first to simulate it's allowed or simulate new write.
        res_write, ok_write = await _write_handler(
            {
                "path": str(workspace_test_file),
                "content": "Line 1: Hello Workspace\nLine 2: Safety First",
            }
        )
        assert ok_write
        assert "Wrote" in res_write

        # Now test read
        res_read, ok_read = await _read_handler({"path": str(workspace_test_file)})
        assert ok_read
        assert "Hello Workspace" in res_read

        # Now test edit (requires file to have been read)
        res_edit, ok_edit = await _edit_handler(
            {
                "path": str(workspace_test_file),
                "old_str": "Safety First",
                "new_str": "Safety Ensured",
            }
        )
        assert ok_edit
        assert "Edited" in res_edit

        # Verify read contains edited value
        res_read_final, ok_read_final = await _read_handler(
            {"path": str(workspace_test_file)}
        )
        assert "Safety Ensured" in res_read_final

    finally:
        # Clean up physically created file
        if workspace_test_file.exists():
            workspace_test_file.unlink()
        _files_read.clear()


@pytest.mark.asyncio
async def test_bash_handler_dangerous_command_with_whitelist(monkeypatch):
    # Set whitelist environment variable to bypass
    monkeypatch.setenv("AIDD_INTERN_DANGEROUS_COMMANDS_WHITELIST", "rm")

    # Mock subprocess.run to avoid actual execution while verifying it bypasses
    import subprocess
    from unittest.mock import MagicMock

    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "whitelisted execution bypassed"
    mock_run.return_value.stderr = ""
    monkeypatch.setattr(subprocess, "run", mock_run)

    res, ok = await _bash_handler({"command": "rm -rf ~"})
    assert ok
    assert "whitelisted execution bypassed" in res


@pytest.mark.asyncio
async def test_bash_handler_interactive_approval_accept(monkeypatch):
    import sys
    import subprocess
    from unittest.mock import MagicMock

    # Mock stdin to be a TTY (interactive)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    # Mock user typing 'y' for yes
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "y")

    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    mock_run.return_value.stdout = "interactive user approved run"
    mock_run.return_value.stderr = ""
    monkeypatch.setattr(subprocess, "run", mock_run)

    res, ok = await _bash_handler({"command": "rm -rf ~"})
    assert ok
    assert "interactive user approved run" in res


@pytest.mark.asyncio
async def test_bash_handler_interactive_approval_reject(monkeypatch):
    import sys

    # Mock stdin to be a TTY (interactive)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    # Mock user typing 'n' for no
    monkeypatch.setattr("builtins.input", lambda *args, **kwargs: "n")

    res, ok = await _bash_handler({"command": "rm -rf ~"})
    assert not ok
    assert "rejected by the user" in res
