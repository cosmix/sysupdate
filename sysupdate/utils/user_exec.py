"""Run user-level tools as the invoking user when sysupdate runs under sudo."""

import os
import pwd
from pathlib import Path
from typing import Any


def user_exec_context() -> tuple[dict[str, Any], str | None]:
    """Return ``(subprocess kwargs, PATH to search)`` for running a user tool.

    Under ``sudo`` user-level tools belong to the invoking user, so commands run
    as ``SUDO_USER`` with that user's home and ``~/.local/bin`` on PATH.
    Otherwise they run as the current user with the inherited env.
    """
    sudo_user = os.environ.get("SUDO_USER")
    if os.geteuid() != 0 or not sudo_user or sudo_user == "root":
        return {}, os.environ.get("PATH")
    try:
        pw = pwd.getpwnam(sudo_user)
    except KeyError:
        return {}, os.environ.get("PATH")

    path = f"{pw.pw_dir}/.local/bin:{os.environ.get('PATH', '')}"
    env = {
        "HOME": pw.pw_dir,
        "USER": pw.pw_name,
        "LOGNAME": pw.pw_name,
        "SHELL": pw.pw_shell,
        "PATH": path,
    }
    env.update({k: os.environ[k] for k in ("LANG", "TERM") if k in os.environ})
    kwargs: dict[str, Any] = {
        "user": pw.pw_uid,
        "group": pw.pw_gid,
        "extra_groups": os.getgrouplist(pw.pw_name, pw.pw_gid),
        "cwd": pw.pw_dir,
        "env": env,
    }
    return kwargs, path


def runs_as_root(exec_kwargs: dict[str, Any]) -> bool:
    """True when commands run with these kwargs would execute as root."""
    return "user" not in exec_kwargs and os.geteuid() == 0


def user_home(exec_kwargs: dict[str, Any]) -> str:
    """Home directory of the user the commands run as."""
    env = exec_kwargs.get("env")
    if env and env.get("HOME"):
        return str(env["HOME"])
    return str(Path.home())
