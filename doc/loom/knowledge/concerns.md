# Concerns & Technical Debt

> Technical debt, warnings, issues, and improvements needed.
> This file is append-only - agents add discoveries, never delete.

(Add concerns as you discover them)

## Missing aiohttp Dependency

test_selfupdate.py imports aiohttp which is not in dependencies. Tests fail to collect when this module loads. Consider adding aiohttp to dev dependencies or removing selfupdate tests if feature is deprecated.
