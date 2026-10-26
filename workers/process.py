"""Timeout ownership for trusted CAD/FEM subprocess trees (not a sandbox)."""
import os
import signal
import subprocess


def run_owned(command, *, timeout, env=None, cwd=None):
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {"start_new_session": True}
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                               env=env, cwd=cwd, **options)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except BaseException:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=15, check=False)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.communicate()
        raise
    return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
