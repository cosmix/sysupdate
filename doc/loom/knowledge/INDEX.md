<!-- generated automatically on knowledge writes — do not edit by hand -->

# Knowledge Index

> Read this index first, then only what it points to: the section for your area in a tier-1 summary (`rg -n '^## ' <file>` lists them) and the tier-2 topics your task touches. A specific question is cheaper to pull than to read — `loom knowledge context --query "..."` returns the matching sections quoted.

## Tier 1 — Summaries

| File | Description | Lines |
| --- | --- | --- |
| [architecture.md](architecture.md) | High-level component relationships, data flow, module dependencies | 175 |
| [entry-points.md](entry-points.md) | Key files agents should read first | 82 |
| [patterns.md](patterns.md) | Architectural patterns discovered in the codebase | 220 |
| [conventions.md](conventions.md) | Coding conventions discovered in the codebase | 188 |
| [mistakes.md](mistakes.md) | Mistakes made and lessons learned - what to avoid | 39 |
| [stack.md](stack.md) | Dependencies, frameworks, and tooling used in the project | 10 |
| [concerns.md](concerns.md) | Technical debt, warnings, and issues to address | 58 |

## Tier 2 — Topics

### architecture

| Topic | Blurb | Lines |
| --- | --- | --- |
| [updater-ordering](architecture/updater-ordering.md) | Updater run order (OrderGate), user-level updaters, Omarchy handling | 7 |

### mistakes

| Topic | Blurb | Lines |
| --- | --- | --- |
| [release-tag-before-main](mistakes/release-tag-before-main.md) | Push main before tagging a release | 10 |
| [subagent-format-scope](mistakes/subagent-format-scope.md) | Glob ruff format touches pre-existing unformatted files | 10 |
| [subagent-git-ops](mistakes/subagent-git-ops.md) | Use git show HEAD:path, never stash, to inspect HEAD | 10 |

### concerns

| Topic | Blurb | Lines |
| --- | --- | --- |
| [pyapp-cpu-variant](concerns/pyapp-cpu-variant.md) | x86_64 binary pins v1 Python; PyApp's v3 default exits silently without AVX2 | 7 |
