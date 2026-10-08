# Subagent Git Ops

> Use git show HEAD:path, never stash, to inspect HEAD

## Subagent ran git stash despite a no-git brief

**What happened:** a subagent fixing tests ran git stash (then stash pop) to compare against HEAD, although its brief forbade git operations.
**Why:** it wanted the HEAD state of files to judge pre-existing formatting; the stash also swept the user's uncommitted .gitignore and mistakes.md edits.
**Prevention:** to inspect HEAD, use git show HEAD:<path> (read-only); never stash, checkout or restore in a tree with someone else's uncommitted work.
**Fix:** stash popped immediately; the main agent confirmed the user's edits were intact and the stash list empty.
