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
  - *Rationale:* Standard patch.object doesn't work on properties without setters


