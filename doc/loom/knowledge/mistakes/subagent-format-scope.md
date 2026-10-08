# Subagent Format Scope

> Glob ruff format touches pre-existing unformatted files

## ruff format run over unowned test files

**What happened:** a subagent ran ruff format on tests/test_*.py, reformatting files outside its ownership, then reverted them with git checkout.
**Why:** about 16 files (tests/ and flatpak.py) are not ruff-formatted at HEAD, so a glob format touches unrelated files.
**Prevention:** run ruff format only on named files you own; never on a glob.
**Fix:** unowned files restored; the format debt remains for a dedicated style commit.
