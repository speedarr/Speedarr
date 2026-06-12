# Releasing Speedarr

## Branches and images

| Branch / tag | Docker image | Built by |
|---|---|---|
| `develop` (every push) | `speedarr/speedarr:develop` | `develop.yml` |
| `vYYYY.MM.DD` tag | `speedarr/speedarr:<version>` + `:latest` | `release.yml` |

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

1. Open a PR from `develop` to `main` and merge it.
2. Go to **Actions → Cut Release → Run workflow** (leave version empty for today's date).

That's it. The workflow:
- tags `main` as `vYYYY.MM.DD` and triggers the release build (`:<version>` + `:latest` Docker images, GitHub Release with auto-generated notes),
- comments "🚀 Fixed in vX" on every issue closed by this release's commits,
- merges `main` back into `develop` automatically (no manual sync step).

**Same-day second release:** run Cut Release again with an explicit version, e.g. `v2026.06.12.1`.

## Hotfixes

PR (or commit) the fix straight to `main`, then run **Cut Release**. The develop
sync is handled by the workflow, so the fix flows back to `develop` automatically.

## Issue lifecycle

- `Fixes #xx` issues close when the PR merges to `main` — on GitHub, **closed means
  "fixed on main"**, not "released".
- The release workflow comments on each closed issue when the build actually ships,
  so watchers know when to pull the new image.

## Notes

- Tags created by Cut Release are pushed with the Actions token, which does not
  fire `on: push: tags` workflows — that's why Cut Release dispatches `release.yml`
  explicitly. Tagging manually from a terminal still works and triggers the build
  directly.
- If the develop sync step fails with a merge conflict, sync manually:
  `git checkout develop && git merge main && git push origin develop`.
- Dependabot version-update PRs target `develop` (see `.github/dependabot.yml`);
  GitHub security-update PRs always target `main` — retarget or cherry-pick as needed.
