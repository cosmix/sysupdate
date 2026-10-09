# Updater Ordering

> Updater run order (OrderGate), user-level updaters, Omarchy handling

## Run order and user-level updaters

Updaters run concurrently except where UpdaterConfig.after (sysupdate/app.py) names predecessors; sysupdate/ordering.py OrderGate makes a dependent wait for the running predecessors and skips it (reported as a failure, 'skipped: <label> update failed') when one failed. Order: Pacman -> Omarchy (omarchy-migrate) -> AUR, because yay/paru and migrations take the pacman db lock. AUR, mise, Omarchy, Claude and Codex run as the invoking user via sysupdate/utils/user_exec.py user_exec_context() (drops to SUDO_USER when root under sudo); AUR is unavailable when it would run as root (makepkg refuses root). On Omarchy (omarchy-migrate found, sysupdate/utils/omarchy.py), pacman runs as 'sudo env OMARCHY_ALLOW_DIRECT_PACMAN=1 pacman -Syu ... --overwrite /usr/share/omarchy/*' (Omarchy's pre-transaction hook aborts a direct pacman upgrade without that variable, and sudo resets the environment), and the Omarchy updater puts the script's bin dir on PATH and sets OMARCHY_PATH, since migrations call other omarchy-* commands. Claude/Codex installed by a system package manager cannot self-update; CliToolUpdater (sysupdate/updaters/cli_tools.py) treats their 'managed by a package manager' / 'Could not detect the Codex installation method' output as success.
