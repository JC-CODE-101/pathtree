import os
import shutil
import subprocess
import tempfile

import pytest


# Ensure that both Bash and Zsh are actually present in the validation environment
# so that they cannot be silently skipped.
def test_ensure_shells_present():
    assert shutil.which("bash") is not None, "Bash shell is required but not found!"
    assert shutil.which("zsh") is not None, "Zsh shell is required but not found!"


@pytest.fixture
def fake_bin_dir():
    real_mktemp = shutil.which("mktemp")
    if not real_mktemp:
        # Fallback to standard location if not found in PATH
        real_mktemp = "/usr/bin/mktemp"

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a fake pathtree executable
        fake_bin = os.path.join(tmpdir, "pathtree")
        with open(fake_bin, "w") as f:
            f.write("""#!/usr/bin/env python3
import sys
import os
import signal

if os.environ.get("FAKE_PATHTREE_SIGINT") == "1":
    os.kill(os.getpid(), signal.SIGINT)
    sys.exit(130)

output_file = None
args = sys.argv[1:]
for i, arg in enumerate(args):
    if arg == "--output" and i + 1 < len(args):
        output_file = args[i + 1]
        break

exit_code = int(os.environ.get("FAKE_PATHTREE_EXIT", "0"))
output_content = os.environ.get("FAKE_PATHTREE_OUTPUT", "")

if output_file and exit_code == 0:
    with open(output_file, "w") as f:
        f.write(output_content)

sys.exit(exit_code)
""")
        os.chmod(fake_bin, 0o755)

        # Create a fake mktemp executable
        fake_mktemp_bin = os.path.join(tmpdir, "mktemp")
        with open(fake_mktemp_bin, "w") as f:
            f.write(f"""#!/usr/bin/env python3
import sys
import os
import subprocess

if os.environ.get("FAKE_MKTEMP_FAIL") == "1":
    sys.stderr.write("mktemp: failed to create temporary file\\n")
    sys.exit(1)

# Otherwise, delegate to the real mktemp
proc = subprocess.run(
    ["{real_mktemp}"] + sys.argv[1:],
    capture_output=True,
    text=True
)
sys.stdout.write(proc.stdout)
sys.stderr.write(proc.stderr)
sys.exit(proc.returncode)
""")
        os.chmod(fake_mktemp_bin, 0o755)

        yield tmpdir


def run_shell(shell_cmd, script, fake_bin_dir, tmp_dir_path, env=None):
    my_env = os.environ.copy()
    my_env["PATH"] = f"{fake_bin_dir}:{my_env['PATH']}"
    my_env["TMPDIR"] = tmp_dir_path
    if env:
        my_env.update(env)

    shell_args = []
    if "bash" in shell_cmd:
        shell_args = ["--noprofile", "--norc"]
    elif "zsh" in shell_cmd:
        shell_args = ["-f"]

    proc = subprocess.run(
        [shell_cmd, *shell_args],
        input=script,
        text=True,
        capture_output=True,
        env=my_env,
    )
    return proc.returncode, proc.stdout, proc.stderr


@pytest.mark.parametrize(
    "shell", [s for s in ["bash", "zsh"] if shutil.which(s)]
)
def test_successful_directory_change(shell, fake_bin_dir):
    with tempfile.TemporaryDirectory() as user_dir:
        target_dir = os.path.join(user_dir, "my_target_dir")
        os.makedirs(target_dir)

        adapter_path = os.path.abspath(f"shell/pathtree.{shell}")
        script = f"""
source "{adapter_path}"
pb
pwd
"""
        env = {"FAKE_PATHTREE_OUTPUT": target_dir, "FAKE_PATHTREE_EXIT": "0"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            ret, stdout, stderr = run_shell(
                shell, script, fake_bin_dir, tmp_dir, env
            )
            assert ret == 0, stderr
            lines = stdout.strip().splitlines()
            assert lines[-1] == os.path.realpath(target_dir)
            assert len(os.listdir(tmp_dir)) == 0


@pytest.mark.parametrize(
    "shell", [s for s in ["bash", "zsh"] if shutil.which(s)]
)
def test_path_with_spaces(shell, fake_bin_dir):
    with tempfile.TemporaryDirectory() as user_dir:
        target_dir = os.path.join(user_dir, "my target dir with spaces")
        os.makedirs(target_dir)

        adapter_path = os.path.abspath(f"shell/pathtree.{shell}")
        script = f"""
source "{adapter_path}"
pb
pwd
"""
        env = {"FAKE_PATHTREE_OUTPUT": target_dir, "FAKE_PATHTREE_EXIT": "0"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            ret, stdout, stderr = run_shell(
                shell, script, fake_bin_dir, tmp_dir, env
            )
            assert ret == 0, stderr
            lines = stdout.strip().splitlines()
            assert lines[-1] == os.path.realpath(target_dir)
            assert len(os.listdir(tmp_dir)) == 0


@pytest.mark.parametrize(
    "shell", [s for s in ["bash", "zsh"] if shutil.which(s)]
)
def test_empty_output_no_change(shell, fake_bin_dir):
    adapter_path = os.path.abspath(f"shell/pathtree.{shell}")
    script = f"""
source "{adapter_path}"
initial_pwd=$(pwd)
pb
pb_status=$?
if [ "$initial_pwd" = "$(pwd)" ]; then
    echo "UNCHANGED"
else
    echo "CHANGED"
fi
echo "STATUS: $pb_status"
"""
    env = {"FAKE_PATHTREE_OUTPUT": "", "FAKE_PATHTREE_EXIT": "0"}

    with tempfile.TemporaryDirectory() as tmp_dir:
        ret, stdout, stderr = run_shell(
            shell, script, fake_bin_dir, tmp_dir, env
        )
        assert ret == 0, stderr
        lines = stdout.strip().splitlines()
        assert "UNCHANGED" in lines
        assert "STATUS: 0" in lines
        assert len(os.listdir(tmp_dir)) == 0


@pytest.mark.parametrize(
    "shell", [s for s in ["bash", "zsh"] if shutil.which(s)]
)
def test_nonexistent_path_no_change(shell, fake_bin_dir):
    adapter_path = os.path.abspath(f"shell/pathtree.{shell}")
    script = f"""
source "{adapter_path}"
initial_pwd=$(pwd)
pb
pb_status=$?
if [ "$initial_pwd" = "$(pwd)" ]; then
    echo "UNCHANGED"
else
    echo "CHANGED"
fi
echo "STATUS: $pb_status"
"""
    env = {
        "FAKE_PATHTREE_OUTPUT": "/nonexistent/path/here",
        "FAKE_PATHTREE_EXIT": "0",
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        ret, stdout, stderr = run_shell(
            shell, script, fake_bin_dir, tmp_dir, env
        )
        assert ret == 0, stderr
        lines = stdout.strip().splitlines()
        assert "UNCHANGED" in lines
        # Confirm that pb returned a non-zero exit status for invalid directory
        has_nonzero = any(
            line.startswith("STATUS: ") and line != "STATUS: 0" for line in lines
        )
        assert has_nonzero
        assert len(os.listdir(tmp_dir)) == 0


@pytest.mark.parametrize(
    "shell", [s for s in ["bash", "zsh"] if shutil.which(s)]
)
def test_file_instead_of_directory_no_change(shell, fake_bin_dir):
    with tempfile.NamedTemporaryFile() as tmp_file:
        adapter_path = os.path.abspath(f"shell/pathtree.{shell}")
        script = f"""
source "{adapter_path}"
initial_pwd=$(pwd)
pb
pb_status=$?
if [ "$initial_pwd" = "$(pwd)" ]; then
    echo "UNCHANGED"
else
    echo "CHANGED"
fi
echo "STATUS: $pb_status"
"""
        env = {"FAKE_PATHTREE_OUTPUT": tmp_file.name, "FAKE_PATHTREE_EXIT": "0"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            ret, stdout, stderr = run_shell(
                shell, script, fake_bin_dir, tmp_dir, env
            )
            assert ret == 0, stderr
            lines = stdout.strip().splitlines()
            assert "UNCHANGED" in lines
            # Verify direct return status of pb is non-zero
            has_nonzero = any(
                line.startswith("STATUS: ") and line != "STATUS: 0" for line in lines
            )
            assert has_nonzero
            assert len(os.listdir(tmp_dir)) == 0


@pytest.mark.parametrize(
    "shell", [s for s in ["bash", "zsh"] if shutil.which(s)]
)
def test_failed_cd_no_change(shell, fake_bin_dir):
    with tempfile.TemporaryDirectory() as user_dir:
        # Create directory with no permissions so cd fails (or simulate cd failing)
        unnavigable_dir = os.path.join(user_dir, "unnavigable")
        os.makedirs(unnavigable_dir)
        os.chmod(unnavigable_dir, 0o000)

        adapter_path = os.path.abspath(f"shell/pathtree.{shell}")
        script = f"""
source "{adapter_path}"
initial_pwd=$(pwd)
pb
pb_status=$?
if [ "$initial_pwd" = "$(pwd)" ]; then
    echo "UNCHANGED"
else
    echo "CHANGED"
fi
echo "STATUS: $pb_status"
"""
        env = {"FAKE_PATHTREE_OUTPUT": unnavigable_dir, "FAKE_PATHTREE_EXIT": "0"}

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                ret, stdout, stderr = run_shell(
                    shell, script, fake_bin_dir, tmp_dir, env
                )
                assert ret == 0, stderr
                lines = stdout.strip().splitlines()
                assert "UNCHANGED" in lines
                # Verify that pb returns a non-zero exit status on cd failure
                has_nonzero = any(
                    line.startswith("STATUS: ") and line != "STATUS: 0"
                    for line in lines
                )
                assert has_nonzero
                assert len(os.listdir(tmp_dir)) == 0
        finally:
            os.chmod(unnavigable_dir, 0o755)


@pytest.mark.parametrize(
    "shell", [s for s in ["bash", "zsh"] if shutil.which(s)]
)
def test_nonzero_exit_no_change(shell, fake_bin_dir):
    adapter_path = os.path.abspath(f"shell/pathtree.{shell}")
    script = f"""
source "{adapter_path}"
initial_pwd=$(pwd)
pb
exit_val=$?
if [ "$initial_pwd" = "$(pwd)" ]; then
    echo "UNCHANGED"
fi
echo "EXIT_STATUS: $exit_val"
"""
    env = {"FAKE_PATHTREE_OUTPUT": "/some/valid/path", "FAKE_PATHTREE_EXIT": "42"}

    with tempfile.TemporaryDirectory() as tmp_dir:
        ret, stdout, stderr = run_shell(
            shell, script, fake_bin_dir, tmp_dir, env
        )
        assert ret == 0, stderr
        lines = stdout.strip().splitlines()
        assert "UNCHANGED" in lines
        assert "EXIT_STATUS: 42" in lines
        assert len(os.listdir(tmp_dir)) == 0


@pytest.mark.parametrize(
    "shell", [s for s in ["bash", "zsh"] if shutil.which(s)]
)
def test_user_traps_remain_unchanged(shell, fake_bin_dir):
    adapter_path = os.path.abspath(f"shell/pathtree.{shell}")
    script = f"""
source "{adapter_path}"
trap 'echo "MyCustomTrap"' SIGINT
pb
trap
"""
    env = {"FAKE_PATHTREE_OUTPUT": "", "FAKE_PATHTREE_EXIT": "0"}

    with tempfile.TemporaryDirectory() as tmp_dir:
        ret, stdout, stderr = run_shell(
            shell, script, fake_bin_dir, tmp_dir, env
        )
        assert ret == 0, stderr
        assert "MyCustomTrap" in stdout
        assert len(os.listdir(tmp_dir)) == 0


@pytest.mark.parametrize(
    "shell", [s for s in ["bash", "zsh"] if shutil.which(s)]
)
def test_no_helper_functions_or_global_variables_remain(shell, fake_bin_dir):
    adapter_path = os.path.abspath(f"shell/pathtree.{shell}")
    script = f"""
source "{adapter_path}"
pb
# Get list of variables after clearing function output from screen
echo "---VARIABLES---"
set
"""
    env = {"FAKE_PATHTREE_OUTPUT": "", "FAKE_PATHTREE_EXIT": "0"}

    with tempfile.TemporaryDirectory() as tmp_dir:
        ret, stdout, stderr = run_shell(
            shell, script, fake_bin_dir, tmp_dir, env
        )
        assert ret == 0, stderr

        # Verify that no helper variables leak into global scope.
        lines = stdout.splitlines()
        variables_started = False
        for line in lines:
            if "---VARIABLES---" in line:
                variables_started = True
                continue
            if not variables_started:
                continue

            # If the line represents a function body line, skip it
            if (
                line.startswith(" ")
                or line.startswith("\t")
                or line.startswith("}")
                or line.startswith("{")
            ):
                continue
            if "pb ()" in line:
                continue

            for pattern in ["temp_file=", "target_path=", "cd_status=", "exit_status="]:
                if pattern in line:
                    raise AssertionError(f"Leaked variable found in set: {line}")


@pytest.mark.parametrize(
    "shell", [s for s in ["bash", "zsh"] if shutil.which(s)]
)
def test_no_parent_shell_signaled(shell, fake_bin_dir):
    adapter_path = os.path.abspath(f"shell/pathtree.{shell}")
    script = f"""
source "{adapter_path}"
pb
echo "STILL_ALIVE"
"""
    env = {"FAKE_PATHTREE_OUTPUT": "", "FAKE_PATHTREE_EXIT": "0"}

    with tempfile.TemporaryDirectory() as tmp_dir:
        ret, stdout, stderr = run_shell(
            shell, script, fake_bin_dir, tmp_dir, env
        )
        assert ret == 0, stderr
        assert "STILL_ALIVE" in stdout
        assert len(os.listdir(tmp_dir)) == 0


@pytest.mark.parametrize(
    "shell", [s for s in ["bash", "zsh"] if shutil.which(s)]
)
def test_real_interruption(shell, fake_bin_dir):
    adapter_path = os.path.abspath(f"shell/pathtree.{shell}")
    script = f"""
source "{adapter_path}"
initial_pwd=$(pwd)
trap 'echo "MyCustomTrap"' SIGINT
pb
pb_status=$?
if [ "$initial_pwd" = "$(pwd)" ]; then
    echo "UNCHANGED"
else
    echo "CHANGED"
fi
echo "STATUS: $pb_status"
trap
echo "STILL_ALIVE"
"""
    env = {"FAKE_PATHTREE_SIGINT": "1"}

    with tempfile.TemporaryDirectory() as tmp_dir:
        ret, stdout, stderr = run_shell(
            shell, script, fake_bin_dir, tmp_dir, env
        )
        # The parent shell process should continue running successfully
        assert ret == 0, stderr
        lines = stdout.strip().splitlines()
        assert "UNCHANGED" in lines
        assert "STILL_ALIVE" in lines
        # pb_status should be non-zero for signal termination
        has_nonzero = any(
            line.startswith("STATUS: ") and line != "STATUS: 0" for line in lines
        )
        assert has_nonzero
        # Custom trap must remain unchanged
        assert any("MyCustomTrap" in line for line in lines)
        # Verify temporary file was deleted
        assert len(os.listdir(tmp_dir)) == 0


@pytest.mark.parametrize(
    "shell", [s for s in ["bash", "zsh"] if shutil.which(s)]
)
def test_mktemp_failure(shell, fake_bin_dir):
    adapter_path = os.path.abspath(f"shell/pathtree.{shell}")
    script = f"""
source "{adapter_path}"
initial_pwd=$(pwd)
pb
pb_status=$?
if [ "$initial_pwd" = "$(pwd)" ]; then
    echo "UNCHANGED"
else
    echo "CHANGED"
fi
echo "STATUS: $pb_status"
"""
    # Instruct fake mktemp to fail
    env = {"FAKE_MKTEMP_FAIL": "1"}

    with tempfile.TemporaryDirectory() as tmp_dir:
        ret, stdout, stderr = run_shell(
            shell, script, fake_bin_dir, tmp_dir, env
        )
        assert ret == 0, stderr
        lines = stdout.strip().splitlines()
        assert "UNCHANGED" in lines
        # pb should return non-zero when mktemp fails
        has_nonzero = any(
            line.startswith("STATUS: ") and line != "STATUS: 0" for line in lines
        )
        assert has_nonzero
        # Ensure no temporary file artifacts remain
        assert len(os.listdir(tmp_dir)) == 0
