# Releasing Speedarr

## Branches and images

| Branch / tag | Docker image | Built by |
|---|---|---|
| `develop` (every push) | `speedarr/speedarr:develop` | `develop.yml` |
| `vYYYY.MM.DD[.N]` tag | `speedarr/speedarr:<version>` + `:latest` | `release.yml` |

## Everyday work

Work on `develop` (conventional commits: `feat:`, `fix:`, `docs:`, `chore:`).
Reference issues with `Fixes #xx` in commit messages — see "Issue lifecycle" below.

```bash
git checkout develop
# make changes...
git add <files>
git commit -m "fix: description"
git push origin develop        # auto-builds :develop image
```

## Cutting a release

1. Open a PR from `develop` to `main` titled `Release vYYYY.MM.DD` (add `.N` for a second release on the same day).
   The PR body is the release notes: `## Highlights`, `## Fixes`, `## Dependencies`, `## Notes for API users` as needed,
   then one `Closes #nn` line per issue the release closes. Leave out the commit list and any "N commits since" line:
   the release page gets GitHub's "What's Changed" list and Full Changelog link appended automatically.
2. Merge it with the default merge message.

That's it. Merging the PR runs **Cut Release**, which tags the merge commit with the version from the PR title and triggers
the release build. The release build pushes `speedarr/speedarr:<version>`, starts it and checks the health endpoint reports
that version, then moves `:latest`, creates the GitHub Release (the PR body followed by GitHub's generated "What's Changed"
list), comments "🚀 Fixed in vX" on every issue closed by the release, and merges `main` back into `develop`.

If the smoke test fails, `:latest` stays on the previous release and no GitHub Release is created. Fix it on `develop`
and open a new release PR titled with the next `.N` version.

**Hotfixes and re-releases:** for a fix committed straight to `main`, or a same-day second release, run
**Actions → Cut Release → Run workflow** with the version filled in (e.g. `v2026.06.12.1`); leave it empty for today's UTC date.
`dry_run` resolves and validates the version without tagging. Anything added to the notes after publication goes through
`gh release edit <tag> --notes-file <file>`.

## Hotfixes

PR (or commit) the fix straight to `main`, then run **Cut Release** manually as described above: a PR merged into `main`
only cuts a release by itself when its title starts with `Release v`. The develop sync is handled by the workflow, so the
fix flows back to `develop` automatically.

## Issue lifecycle

- Issues referenced with `Fixes #xx` in a commit message or `Closes #xx` in the release PR body close when the PR
  merges to `main` — on GitHub, **closed means "fixed on main"**, not "released".
- The release workflow comments on each of those issues when the build actually ships (it scans the commits since the
  previous tag and the release PR body), so watchers know when to pull the new image.

## Notes

- Tags created by Cut Release are pushed with the Actions token, which does not
  fire `on: push: tags` workflows — that's why Cut Release dispatches `release.yml`
  explicitly. Tagging manually from a terminal still works and triggers the build
  directly; with no release PR to take them from, the notes are GitHub's generated ones only.
- If no Cut Release run appears after merging a release PR, run it manually with the version from the PR title
  (`dry_run` first to see the version resolve, then for real).
- If the develop sync step fails with a merge conflict, sync manually:
  `git checkout develop && git merge main && git push origin develop`.
- Dependabot version-update PRs target `develop` (see `.github/dependabot.yml`);
  GitHub security-update PRs always target `main` — retarget or cherry-pick as needed.
