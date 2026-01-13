"""Pytest configuration and fixtures."""

import pytest
from unittest.mock import AsyncMock


@pytest.fixture(autouse=True)
def clear_availability_cache():
    """Clear the command availability cache before each test."""
    from sysupdate.utils import _availability_cache
    _availability_cache.clear()
    yield
    _availability_cache.clear()


@pytest.fixture
def mock_subprocess():
    """Create a mock subprocess for testing."""
    mock_proc = AsyncMock()
    mock_proc.returncode = 0
    mock_proc.stdout = AsyncMock()
    mock_proc.stdout.readline = AsyncMock(return_value=b"")
    mock_proc.wait = AsyncMock()
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    return mock_proc


@pytest.fixture
def apt_update_output():
    """Sample APT update output."""
    return """
Hit:1 http://archive.ubuntu.com/ubuntu jammy InRelease
Get:2 http://archive.ubuntu.com/ubuntu jammy-updates InRelease [119 kB]
Get:3 http://archive.ubuntu.com/ubuntu jammy-security InRelease [110 kB]
Fetched 229 kB in 1s (229 kB/s)
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
5 packages can be upgraded. Run 'apt list --upgradable' to see them.
"""


@pytest.fixture
def apt_upgrade_output():
    """Sample APT upgrade output."""
    return """
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
Calculating upgrade... Done
The following packages will be upgraded:
  libssl3 openssl python3.11 python3.11-minimal wget
5 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
Need to get 15.2 MB of archives.
After this operation, 0 B of additional disk space will be used.
Get:1 http://archive.ubuntu.com/ubuntu jammy-updates/main amd64 libssl3 amd64 3.0.13-0ubuntu1 [1,234 kB]
Get:2 http://archive.ubuntu.com/ubuntu jammy-updates/main amd64 openssl amd64 3.0.13-0ubuntu1 [987 kB]
Fetched 15.2 MB in 3s (5,067 kB/s)
(Reading database ... 250000 files and directories currently installed.)
Preparing to unpack .../libssl3_3.0.13-0ubuntu1_amd64.deb ...
Unpacking libssl3:amd64 (3.0.13) over (3.0.11) ...
Unpacking openssl (3.0.13) over (3.0.11) ...
Unpacking python3.11 (3.11.8-1) over (3.11.6-1) ...
Unpacking python3.11-minimal (3.11.8-1) over (3.11.6-1) ...
Unpacking wget (1.21.4-1) over (1.21.3-1) ...
Setting up libssl3:amd64 (3.0.13) ...
Setting up openssl (3.0.13) ...
Setting up python3.11-minimal (3.11.8-1) ...
Setting up python3.11 (3.11.8-1) ...
Setting up wget (1.21.4-1) ...
Processing triggers for man-db (2.10.2-1) ...
Processing triggers for libc-bin (2.35-0ubuntu3.1) ...
"""


@pytest.fixture
def apt_no_updates_output():
    """Sample APT output when no updates available."""
    return """
Reading package lists... Done
Building dependency tree... Done
Reading state information... Done
Calculating upgrade... Done
0 upgraded, 0 newly installed, 0 to remove and 0 not upgraded.
All packages are up to date.
"""


@pytest.fixture
def flatpak_update_output():
    """Sample Flatpak update output."""
    return """
Looking for updates...

        ID                                      Branch         Op
 1.     org.mozilla.firefox                     stable         u
 2.     org.gimp.GIMP                           stable         u
 3.     org.libreoffice.LibreOffice             stable         u
 4.     org.freedesktop.Platform.GL.default    22.08          u
 5.     org.gnome.Platform.Locale              45             u

Downloading org.mozilla.firefox... 45%
Downloading org.mozilla.firefox... 100%
Installing org.mozilla.firefox
Downloading org.gimp.GIMP... 100%
Installing org.gimp.GIMP
Downloading org.libreoffice.LibreOffice... 100%
Installing org.libreoffice.LibreOffice

Changes complete.
"""


@pytest.fixture
def flatpak_no_updates_output():
    """Sample Flatpak output when no updates available."""
    return """
Looking for updates...
Nothing to do.
"""
