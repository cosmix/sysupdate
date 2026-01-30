"""Binary detection and replacement utilities for self-update."""

import asyncio
import os
import platform
import shutil
import sys
from pathlib import Path


def get_architecture() -> str:
    """Detect system architecture.

    Returns:
        "x86_64" or "aarch64"

    Raises:
        RuntimeError: If architecture is not supported
    """
    machine = platform.machine().lower()

    arch_map = {
        "x86_64": "x86_64",
        "amd64": "x86_64",
        "aarch64": "aarch64",
        "arm64": "aarch64",
    }

    arch = arch_map.get(machine)
    if arch is None:
        raise RuntimeError(
            f"Unsupported architecture: {machine}. "
            "Supported architectures: x86_64, aarch64"
        )

    return arch


def get_binary_path() -> Path:
    """Find the current sysupdate binary path.

    For PyApp binaries, the actual binary is the parent process that spawned
    the embedded Python interpreter. We find it via /proc/<ppid>/exe.

    Returns:
        Path to current binary

    Raises:
        RuntimeError: If binary cannot be found
    """
    # Check parent process first (for PyApp: the wrapper that spawned Python)
    ppid = os.getppid()
    try:
        parent_exe = Path(f"/proc/{ppid}/exe").resolve()
        if parent_exe.name == "sysupdate":
            return parent_exe
    except (OSError, PermissionError):
        pass

    # Check sys.executable (for direct PyApp or venv installs)
    if sys.executable:
        exe_path = Path(sys.executable)
        if exe_path.name in ("sysupdate", "sysupdate.exe"):
            return exe_path

    # Check PATH
    which_result = shutil.which("sysupdate")
    if which_result:
        return Path(which_result).resolve()

    raise RuntimeError(
        "Could not locate sysupdate binary. "
        "Please ensure sysupdate is installed and in PATH."
    )


def get_expected_asset_name(arch: str) -> str:
    """Get expected GitHub release asset name for architecture.

    Args:
        arch: Architecture string ("x86_64" or "aarch64")

    Returns:
        Expected asset name format: "sysupdate-linux-{arch}"
    """
    return f"sysupdate-linux-{arch}"


def can_write_to_path(path: Path) -> bool:
    """Check if we have write permission to a path.

    Args:
        path: Path to check

    Returns:
        True if writable, False otherwise
    """
    if not path.exists():
        # Check parent directory
        return can_write_to_path(path.parent) if path.parent != path else False

    # For existing files/directories, check write permission
    return os.access(path, os.W_OK)


async def replace_binary(
    current_path: Path,
    new_binary_path: Path,
) -> tuple[bool, str]:
    """Replace the current binary with a new one atomically.

    Uses sudo if write permission is not available.
    Replacement is atomic using rename to avoid corruption.

    Args:
        current_path: Path to current binary
        new_binary_path: Path to new binary (will be moved, not copied)

    Returns:
        Tuple of (success, error_message)
        On success, error_message is empty string
    """
    if not new_binary_path.exists():
        return False, f"New binary does not exist: {new_binary_path}"

    if not new_binary_path.is_file():
        return False, f"New binary path is not a file: {new_binary_path}"

    if not current_path.exists():
        return False, f"Current binary does not exist: {current_path}"

    # Make new binary executable
    try:
        new_binary_path.chmod(0o755)
    except PermissionError:
        return False, f"Cannot make new binary executable: {new_binary_path}"

    # Check if we need sudo
    needs_sudo = not can_write_to_path(current_path)

    # Create backup path (same directory as current)
    backup_path = current_path.with_suffix(".bak")

    try:
        if needs_sudo:
            # Use sudo for the entire operation
            success, error = await _replace_with_sudo(
                current_path, new_binary_path, backup_path
            )
        else:
            # Direct replacement without sudo
            success, error = await _replace_direct(
                current_path, new_binary_path, backup_path
            )

        return success, error

    except Exception as e:
        return False, f"Unexpected error during binary replacement: {e}"


async def _replace_with_sudo(
    current_path: Path,
    new_binary_path: Path,
    backup_path: Path,
) -> tuple[bool, str]:
    """Replace binary using sudo commands.

    Args:
        current_path: Path to current binary
        new_binary_path: Path to new binary
        backup_path: Path to backup current binary

    Returns:
        Tuple of (success, error_message)
    """
    # Step 1: Backup current binary
    proc = await asyncio.create_subprocess_exec(
        "sudo", "mv", str(current_path), str(backup_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        error = stderr.decode().strip() if stderr else "Failed to backup current binary"
        return False, f"Backup failed: {error}"

    # Step 2: Move new binary to target location
    proc = await asyncio.create_subprocess_exec(
        "sudo", "mv", str(new_binary_path), str(current_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        error = stderr.decode().strip() if stderr else "Failed to move new binary"
        # Restore backup
        restore_proc = await asyncio.create_subprocess_exec(
            "sudo", "mv", str(backup_path), str(current_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await restore_proc.communicate()
        return False, f"Move failed: {error}. Backup restored."

    # Step 3: Remove backup on success
    proc = await asyncio.create_subprocess_exec(
        "sudo", "rm", str(backup_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    await proc.communicate()

    return True, ""


async def _replace_direct(
    current_path: Path,
    new_binary_path: Path,
    backup_path: Path,
) -> tuple[bool, str]:
    """Replace binary directly without sudo.

    Args:
        current_path: Path to current binary
        new_binary_path: Path to new binary
        backup_path: Path to backup current binary

    Returns:
        Tuple of (success, error_message)
    """
    try:
        # Step 1: Backup current binary
        shutil.move(str(current_path), str(backup_path))

        # Step 2: Move new binary to target location
        try:
            shutil.move(str(new_binary_path), str(current_path))
        except Exception as e:
            # Restore backup on failure
            shutil.move(str(backup_path), str(current_path))
            return False, f"Move failed: {e}. Backup restored."

        # Step 3: Remove backup on success
        backup_path.unlink(missing_ok=True)

        return True, ""

    except Exception as e:
        return False, f"Direct replacement failed: {e}"
