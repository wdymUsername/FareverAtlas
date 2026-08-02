#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

exec cargo build \
    --release \
    --target x86_64-pc-windows-gnu \
    --manifest-path "$ROOT/Cargo.toml"

