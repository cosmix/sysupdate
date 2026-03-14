"""Tests for the aria2 installation helper utilities."""

from unittest.mock import AsyncMock, MagicMock, patch

from sysupdate.utils.aria2 import (
    _detect_install_command,
    _install_aria2,
    _install_hint,
    prompt_install_aria2,
)


class TestDetectInstallCommand:
    """Tests for _detect_install_command."""

    def test_detects_apt(self):
        """Test that apt-based systems return the correct install command."""
        with patch("shutil.which", side_effect=lambda cmd: "/usr/bin/apt" if cmd == "apt" else None):
            result = _detect_install_command()
        assert result == ["sudo", "apt", "install", "-y", "aria2"]

    def test_detects_dnf(self):
        """Test that dnf-based systems return the correct install command."""
        with patch(
            "shutil.which",
            side_effect=lambda cmd: "/usr/bin/dnf" if cmd == "dnf" else None,
        ):
            result = _detect_install_command()
        assert result == ["sudo", "dnf", "install", "-y", "aria2"]

    def test_detects_pacman(self):
        """Test that pacman-based systems return the correct install command."""
        with patch(
            "shutil.which",
            side_effect=lambda cmd: "/usr/bin/pacman" if cmd == "pacman" else None,
        ):
            result = _detect_install_command()
        assert result == ["sudo", "pacman", "-S", "--noconfirm", "aria2"]

    def test_returns_none_when_no_package_manager(self):
        """Test that None is returned when no supported package manager is found."""
        with patch("shutil.which", return_value=None):
            result = _detect_install_command()
        assert result is None

    def test_apt_takes_priority_over_dnf(self):
        """Test that apt is preferred when multiple package managers exist."""
        with patch(
            "shutil.which",
            side_effect=lambda cmd: f"/usr/bin/{cmd}" if cmd in ("apt", "dnf") else None,
        ):
            result = _detect_install_command()
        assert result is not None
        assert result[1] == "apt"


class TestInstallHint:
    """Tests for _install_hint."""

    def test_hint_for_apt(self):
        """Test hint message for apt-based systems."""
        with patch("shutil.which", side_effect=lambda cmd: "/usr/bin/apt" if cmd == "apt" else None):
            hint = _install_hint()
        assert hint == "sudo apt install aria2"

    def test_hint_for_dnf(self):
        """Test hint message for dnf-based systems."""
        with patch(
            "shutil.which",
            side_effect=lambda cmd: "/usr/bin/dnf" if cmd == "dnf" else None,
        ):
            hint = _install_hint()
        assert hint == "sudo dnf install aria2"

    def test_hint_for_pacman(self):
        """Test hint message for pacman-based systems."""
        with patch(
            "shutil.which",
            side_effect=lambda cmd: "/usr/bin/pacman" if cmd == "pacman" else None,
        ):
            hint = _install_hint()
        assert hint == "sudo pacman -S aria2"

    def test_hint_fallback(self):
        """Test fallback hint message when no package manager is found."""
        with patch("shutil.which", return_value=None):
            hint = _install_hint()
        assert hint == "your package manager"


class TestPromptInstallAria2:
    """Tests for prompt_install_aria2."""

    async def test_user_declines_installation(self):
        """Test that declining the prompt returns False without attempting install."""
        console = MagicMock()

        with patch("asyncio.get_running_loop") as mock_loop_func:
            mock_loop = MagicMock()
            mock_loop_func.return_value = mock_loop
            # run_in_executor returns a coroutine that yields False (user says no)
            mock_loop.run_in_executor = AsyncMock(return_value=False)

            result = await prompt_install_aria2(console)

        assert result is False

    async def test_user_accepts_installation_and_install_succeeds(self):
        """Test that accepting the prompt triggers installation."""
        console = MagicMock()

        with patch("asyncio.get_running_loop") as mock_loop_func:
            mock_loop = MagicMock()
            mock_loop_func.return_value = mock_loop
            mock_loop.run_in_executor = AsyncMock(return_value=True)

            with patch(
                "sysupdate.utils.aria2._install_aria2",
                new_callable=AsyncMock,
                return_value=True,
            ) as mock_install:
                result = await prompt_install_aria2(console)

        assert result is True
        mock_install.assert_awaited_once_with(console)

    async def test_user_accepts_but_install_fails(self):
        """Test that a failed installation returns False."""
        console = MagicMock()

        with patch("asyncio.get_running_loop") as mock_loop_func:
            mock_loop = MagicMock()
            mock_loop_func.return_value = mock_loop
            mock_loop.run_in_executor = AsyncMock(return_value=True)

            with patch(
                "sysupdate.utils.aria2._install_aria2",
                new_callable=AsyncMock,
                return_value=False,
            ):
                result = await prompt_install_aria2(console)

        assert result is False


class TestInstallAria2:
    """Tests for _install_aria2."""

    async def test_no_package_manager_detected(self):
        """Test that missing package manager returns False."""
        console = MagicMock()

        with patch("sysupdate.utils.aria2._detect_install_command", return_value=None):
            result = await _install_aria2(console)

        assert result is False

    async def test_successful_installation(self):
        """Test successful installation via subprocess."""
        console = MagicMock()

        mock_process = AsyncMock()
        mock_process.wait = AsyncMock(return_value=0)

        async def mock_stdout_iter():
            yield b"Reading package lists...\n"
            yield b"Setting up aria2...\n"

        mock_process.stdout = mock_stdout_iter()

        with patch(
            "sysupdate.utils.aria2._detect_install_command",
            return_value=["sudo", "apt", "install", "-y", "aria2"],
        ):
            with patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ):
                with patch("sysupdate.utils.aria2.invalidate_cache") as mock_invalidate:
                    result = await _install_aria2(console)

        assert result is True
        mock_invalidate.assert_called_once_with("aria2c")

    async def test_failed_installation_nonzero_exit(self):
        """Test that nonzero exit code from installer returns False."""
        console = MagicMock()

        mock_process = AsyncMock()
        mock_process.wait = AsyncMock(return_value=1)

        async def mock_stdout_iter():
            yield b"E: Unable to locate package aria2\n"

        mock_process.stdout = mock_stdout_iter()

        with patch(
            "sysupdate.utils.aria2._detect_install_command",
            return_value=["sudo", "apt", "install", "-y", "aria2"],
        ):
            with patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ):
                result = await _install_aria2(console)

        assert result is False

    async def test_installation_exception(self):
        """Test that exceptions during installation are caught and return False."""
        console = MagicMock()

        with patch(
            "sysupdate.utils.aria2._detect_install_command",
            return_value=["sudo", "apt", "install", "-y", "aria2"],
        ):
            with patch(
                "asyncio.create_subprocess_exec",
                side_effect=PermissionError("sudo requires a password"),
            ):
                result = await _install_aria2(console)

        assert result is False

    async def test_successful_install_invalidates_cache(self):
        """Test that successful install invalidates the aria2c availability cache."""
        console = MagicMock()

        mock_process = AsyncMock()
        mock_process.wait = AsyncMock(return_value=0)

        async def mock_stdout_iter():
            return
            yield  # pragma: no cover

        mock_process.stdout = mock_stdout_iter()

        with patch(
            "sysupdate.utils.aria2._detect_install_command",
            return_value=["sudo", "apt", "install", "-y", "aria2"],
        ):
            with patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ):
                with patch("sysupdate.utils.aria2.invalidate_cache") as mock_invalidate:
                    await _install_aria2(console)

        mock_invalidate.assert_called_once_with("aria2c")

    async def test_failed_install_does_not_invalidate_cache(self):
        """Test that failed install does NOT invalidate the availability cache."""
        console = MagicMock()

        mock_process = AsyncMock()
        mock_process.wait = AsyncMock(return_value=1)

        async def mock_stdout_iter():
            return
            yield  # pragma: no cover

        mock_process.stdout = mock_stdout_iter()

        with patch(
            "sysupdate.utils.aria2._detect_install_command",
            return_value=["sudo", "apt", "install", "-y", "aria2"],
        ):
            with patch(
                "asyncio.create_subprocess_exec",
                return_value=mock_process,
            ):
                with patch("sysupdate.utils.aria2.invalidate_cache") as mock_invalidate:
                    await _install_aria2(console)

        mock_invalidate.assert_not_called()
