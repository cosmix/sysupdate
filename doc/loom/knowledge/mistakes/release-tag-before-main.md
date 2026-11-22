# Release Tag Before Main

> Push main before tagging a release

## Release tag pushed before main

**What happened:** Pushed a release tag for an unpushed main commit before pushing main.
**Why:** Treated pushing the tag alone as sufficient to publish the commit.
**Prevention:** Before cutting a release, push the intended main commit and verify remote main points to it before pushing the tag.
**Fix:** Pushed main to the tagged commit and verified both remote refs.
