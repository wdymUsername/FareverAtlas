# Agent notes — FareverAtlas

## Releases

- **Only** the rolling GitHub Release tag **`Nightly`** is allowed.
- Do **not** create, push, or restore `v*` / semver tags or any other release tags.
- Do **not** add workflow triggers for `push: tags: v*` or `release: published`.
- Pushing an old tag runs the workflow file **from that tagged commit**, which can resurrect dead versioned releases.
- Stray non-Nightly tags/releases should be deleted; keep Nightly as Latest.
- The portable Windows workflow is **`workflow_dispatch` only**. Do not add schedule, `push`, or `pull_request` triggers.

See `.cursor/rules/nightly-only-releases.mdc` and `.github/workflows/enforce-nightly-only.yml`.
