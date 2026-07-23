"""Shared Rich console instance for the update command path.

A single Console per process keeps terminal/encoding/color detection
consistent across the pre-flight sudo prompt and the main CLI, and avoids
re-running that detection for every module that needs to print.
"""

from rich.console import Console

console = Console()
