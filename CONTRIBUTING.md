# Contributing to Farever Atlas

Contributions, bug fixes and improvements are welcome.

Please keep changes **focused and easy to review**.

---

## Development Setup

### Linux / Proton

```bash
./farever setup
./farever start --dev
```

`setup` creates the Python environment, installs the required packages and
builds the native bridge. Run it again after pulling updates so the bridge stays
current.

Start Farever through Steam and log in before a live session.

Day to day you usually only need `./farever start --dev`; re-run `setup` when
deps or the bridge change.

### Windows

```bat
farever.bat setup
farever.bat start --dev
```

The native bridge must already be built and available at:

```text
native_bridge\farever-atlas-bridge.exe
```

See [`native_bridge/README.md`](native_bridge/README.md) for bridge build
details.

---

## Development Mode

`--dev` enables extra tools intended for development and testing:

- Soft **Reload** and **Toast** controls
- Fog-of-war layer / bake authoring on the map
- Experimental pages such as the **Planner** and **Codex** (otherwise gated as
  Coming soon)

These unfinished features may be incomplete, broken or change without warning.

---

## Keep the Bridge Read-Only

This is an important project rule.

The native bridge may **read** Farever memory, but must never:

- Write to game memory
- Inject code
- Simulate player input
- Automate gameplay
- Add networking to the bridge

Unknown or unsupported Farever builds must **fail safely** instead of guessing
memory locations.

Before changing live game data wiring (or proposing new map / companion
features that need it), read
[`native_bridge/README.md`](native_bridge/README.md). It documents the current
telemetry contract: connected snapshot fields, sweep ranges / caps, `ui` /
`collection` / `codex_units`, build and Proton run notes, and profiling. Use
that as the source of truth for what the bridge already exposes and what is
still off-limits.

---

## Code Style

Python code targets **Python 3.10+**.

The project uses:

- Black
- Ruff
- 99-character line length

Try to follow the existing naming, structure and style of the code around your
changes.

Avoid unrelated cleanup or large rewrites in the same pull request.

---

## Testing

Before opening a pull request:

1. Run Atlas and test the area you changed.
2. Check that existing related features still work.
3. Test against a supported Farever build when your change uses live game data.
4. Mention anything you could not test.

For UI changes, screenshots are useful when they help show the difference.

GitHub Actions builds the portable Windows version for relevant pull requests.

---

## Local Files

Do not commit personal or generated runtime data.

Respect `.gitignore` and do not force-add things such as user settings,
telemetry, virtual environments, logs, API keys or other local files.

---

## Pull Requests

Branch from `main` and keep each pull request focused on one change or closely
related group of changes.

In the pull request, briefly explain:

- **What changed**
- **Why**
- **How you tested it**

If something is unfinished, say so clearly.

---

## Releases

Farever Atlas uses a single rolling release:

**`Nightly`**

Do **not** create:

- Versioned `v*` tags
- Semantic-version release tags
- Additional release tags
- Workflows that publish separate releases

Pull requests may build artifacts for testing, but they must not publish
releases.

Release publishing is handled automatically from `main`.

---

## Questions / Bugs

For bugs, feature requests or other project discussion, open a GitHub issue.

When reporting a bug, include enough information to reproduce it where possible.
