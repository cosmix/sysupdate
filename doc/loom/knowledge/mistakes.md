# Mistakes & Lessons Learned

> Record mistakes made during development and how to avoid them.
> This file is append-only - agents add discoveries, never delete.
>
> Format: Describe what went wrong, why, and how to avoid it next time.

(Add mistakes and lessons as you encounter them)

## Promoted from Memory [2026-01-30 20:16]

### Notes

- Added tests for dry-run indicator (header shows DRY RUN text), ASCII fallback (Console.encoding mocking via PropertyMock), and exit codes (0 on success, 1 on failure, 130 on keyboard interrupt)

### Decisions

- **Used PropertyMock pattern for Console.encoding tests because Rich Console.encoding is a read-only property**
  - _Rationale:_ Standard patch.object doesn't work on properties without setters

## Hand-assembled ASCII-art wordmark corruption (banner, 2026-07-17)

**What happened:** The ANSI Shadow "sysupdate" wordmark in banner.py was assembled by hand-concatenating per-letter rows; row 5 duplicated the D's bottom row into the A's slot and dropped the E's row entirely, corrupting A/T/E on screen.
**Why:** Manual concatenation of 9 letters x 6 rows of visually similar box-drawing strings; the uniform-width test could not catch it because the wrong row happened to have the correct total width.
**Prevention:** Generate multi-letter figlet/ANSI-Shadow art with a script that joins a per-letter glyph table (see the generator snippet approach), then paste the output. Verify by rendering the plain text and reading the actual letters, not just checking row widths.
**Fix:** Rebuilt the rows letter-by-letter programmatically and replaced row 5.

## DNF test mock ordering bug (integration-verify, 2026-03-14)

**What happened:** test_run_update_progress_callback had 4 entries in mock side_effect but only 3 subprocess calls are made by \_do_upgrade(). The duplicate mock_check_proc caused wrong mocks to be used for \_get_current_versions and upgrade process.
**Why:** Comment said "First check in run_update, Second check in \_run_dnf_upgrade" but BaseUpdater.run_update() doesn't call check_updates() for non-dry-run — it delegates directly to \_do_upgrade().
**How to avoid:** Count actual subprocess calls in the code path being tested before setting up side_effect lists. Also set `process.kill = MagicMock()` (not AsyncMock) since Process.kill() is synchronous.
