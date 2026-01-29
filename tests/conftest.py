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


@pytest.fixture
def snap_refresh_list_output():
    """Sample snap refresh --list output showing available updates."""
    return """Name                  Version    Rev    Size    Publisher        Notes
firefox               125.0.1    4432   279MB   mozilla✓         -
vlc                   3.0.20     3650   485MB   videolan✓        -
spotify               1.2.31     71     181MB   spotify✓         -
"""


@pytest.fixture
def snap_list_output():
    """Sample snap list output showing installed versions."""
    return """Name                  Version    Rev    Tracking         Publisher   Notes
core22                20240111   1122   latest/stable    canonical✓  base
firefox               124.0.2    4336   latest/stable    mozilla✓    -
gnome-42-2204         0+git.510  176    latest/stable    canonical✓  -
gtk-common-themes     0.1-81-g442e511  1535   latest/stable    canonical✓  -
snapd                 2.61.3     21184  latest/stable    canonical✓  snapd
spotify               1.2.28     69     latest/stable    spotify✓    -
vlc                   3.0.18     3499   latest/stable    videolan✓   -
"""


@pytest.fixture
def snap_refresh_output():
    """Sample snap refresh output during actual update."""
    return """firefox (stable) 125.0.1 from Mozilla✓ refreshed
vlc (stable) 3.0.20 from VideoLAN✓ refreshed
spotify (stable) 1.2.31 from Spotify✓ refreshed
"""


@pytest.fixture
def snap_no_updates_output():
    """Sample snap refresh --list output when no updates available."""
    return """All snaps up to date.
"""


@pytest.fixture
def dnf_check_update_output():
    """Sample DNF check-update output showing available updates."""
    return """Last metadata expiration check: 0:15:42 ago on Thu Jan 11 10:00:00 2024.

kernel.x86_64                   6.6.9-200.fc39             updates
openssl-libs.x86_64             3.1.4-2.fc39               updates
python3.x86_64                  3.12.1-1.fc39              updates
vim-minimal.x86_64              9.1.016-1.fc39             updates
"""


@pytest.fixture
def dnf_no_updates_output():
    """Sample DNF check-update output when no updates available."""
    return """Last metadata expiration check: 0:15:42 ago on Thu Jan 11 10:00:00 2024.
"""


@pytest.fixture
def dnf_upgrade_output():
    """Sample DNF upgrade output during actual update with download and transaction phases."""
    return """Dependencies resolved.
================================================================================
 Package                 Arch        Version                 Repository    Size
================================================================================
Upgrading:
 kernel                  x86_64      6.6.9-200.fc39          updates      168 M
 openssl-libs            x86_64      3.1.4-2.fc39            updates      2.1 M

Transaction Summary
================================================================================
Upgrade  2 Packages

Total download size: 170 M
Downloading Packages:
(1/2): openssl-libs-3.1.4-2.fc39.x86_64.rpm      100% | 2.1 MB/s |  2.1 MB  00:01
(2/2): kernel-6.6.9-200.fc39.x86_64.rpm          100% | 5.0 MB/s | 168 MB  00:33
--------------------------------------------------------------------------------
Total                                            5.0 MB/s | 170 MB  00:34
Running transaction check
Transaction check succeeded.
Running transaction test
Transaction test succeeded.
Running transaction
  Upgrading        : openssl-libs-3.1.4-2.fc39.x86_64                       1/4
  Upgrading        : kernel-6.6.9-200.fc39.x86_64                           2/4
  Cleanup          : openssl-libs-3.1.3-1.fc39.x86_64                       3/4
  Cleanup          : kernel-6.5.0-100.fc39.x86_64                           4/4
  Verifying        : openssl-libs-3.1.4-2.fc39.x86_64                       1/4
  Verifying        : openssl-libs-3.1.3-1.fc39.x86_64                       2/4
  Verifying        : kernel-6.6.9-200.fc39.x86_64                           3/4
  Verifying        : kernel-6.5.0-100.fc39.x86_64                           4/4

Upgraded:
  kernel-6.6.9-200.fc39.x86_64         openssl-libs-3.1.4-2.fc39.x86_64

Complete!
"""


@pytest.fixture
def dnf_list_installed_output():
    """Sample DNF list installed output showing current versions."""
    return """Installed Packages
kernel.x86_64                    6.5.0-100.fc39                      @updates
openssl-libs.x86_64              3.1.3-1.fc39                        @updates
python3.x86_64                   3.12.0-1.fc39                       @fedora
vim-minimal.x86_64               9.1.015-1.fc39                      @updates
"""
