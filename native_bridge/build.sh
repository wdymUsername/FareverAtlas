#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${CARGO_TARGET_DIR:-$ROOT/target}"
BUILT="$TARGET_DIR/x86_64-pc-windows-gnu/release/farever-atlas-bridge.exe"
DEST="$ROOT/farever-atlas-bridge.exe"
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' "$ROOT/Cargo.toml" | head -n1)"

cargo build \
    --release \
    --target x86_64-pc-windows-gnu \
    --manifest-path "$ROOT/Cargo.toml"

cp -f "$BUILT" "$DEST"
echo "Wrote $DEST (v${VERSION})"
