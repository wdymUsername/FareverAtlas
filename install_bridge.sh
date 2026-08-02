#!/usr/bin/env bash
set -euo pipefail

readonly ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly SOURCE="$ROOT/plugin/nyx_farever_external_bridge.lua"
readonly GAME_DIR_FILE="$ROOT/nyx_game_dir.conf"
readonly APP_ID=3672400

declare -a STEAM_ROOTS=()

add_steam_root() {
    local path="$1"
    local existing

    [[ -d "$path" ]] || return 0
    for existing in "${STEAM_ROOTS[@]}"; do
        [[ "$existing" == "$path" ]] && return 0
    done
    STEAM_ROOTS+=("$path")
}

load_steam_roots() {
    local base
    local path
    local vdf

    add_steam_root "$HOME/.local/share/Steam"
    add_steam_root "$HOME/.steam/steam"
    add_steam_root "$HOME/.var/app/com.valvesoftware.Steam/.local/share/Steam"

    for path in \
        "$HOME"/Games/*/steam \
        "$HOME"/Games/*/SteamLibrary \
        "$HOME"/SteamLibrary; do
        add_steam_root "$path"
    done

    for base in "$HOME/.local/share/Steam" "$HOME/.steam/steam"; do
        vdf="$base/steamapps/libraryfolders.vdf"
        [[ -f "$vdf" ]] || continue
        while IFS= read -r path; do
            path="${path//\\\\/\\}"
            add_steam_root "$path"
        done < <(sed -n 's/.*"path"[[:space:]]*"\([^"]*\)".*/\1/p' "$vdf")
    done
}

detect_game_dir() {
    local detected
    local install_dir
    local manifest
    local steam_root

    load_steam_roots
    for steam_root in "${STEAM_ROOTS[@]}"; do
        manifest="$steam_root/steamapps/appmanifest_${APP_ID}.acf"
        install_dir="Farever"
        if [[ -f "$manifest" ]]; then
            detected="$(
                sed -n 's/.*"installdir"[[:space:]]*"\([^"]*\)".*/\1/p' \
                    "$manifest" \
                    | head -n 1
            )"
            [[ -n "$detected" ]] && install_dir="$detected"
        fi

        if [[ -f "$steam_root/steamapps/common/$install_dir/Farever.exe" ]]; then
            printf '%s\n' "$steam_root/steamapps/common/$install_dir"
            return 0
        fi
    done
    return 1
}

resolve_game_dir() {
    local game_dir

    if [[ $# -ge 1 ]]; then
        game_dir="${1%/}"
    else
        game_dir="$(detect_game_dir || true)"
    fi

    if [[ -z "$game_dir" ]]; then
        echo "Farever installation was not auto-detected." >&2
        echo "Run this script again with the game directory:" >&2
        echo "  $0 /path/to/steamapps/common/Farever" >&2
        return 1
    fi

    if [[ ! -f "$game_dir/Farever.exe" ]]; then
        echo "Farever.exe was not found in: $game_dir" >&2
        return 1
    fi

    printf '%s\n' "$game_dir"
}

install_bridge() {
    local game_dir="$1"
    local legacy_target
    local map_file
    local target
    local target_dir

    target_dir="$game_dir/data/plugins"
    legacy_target="$target_dir/farever_external_bridge.lua"
    target="$target_dir/nyx_farever_external_bridge.lua"
    map_file="$game_dir/data/maps/W1_Siagarta.preview.png"

    mkdir -p "$target_dir"
    if [[ -f "$legacy_target" ]]; then
        rm -f -- "$legacy_target"
        printf 'Removed legacy unprefixed bridge:\n  %s\n' "$legacy_target"
    fi

    install -m 0644 "$SOURCE" "$target"
    printf '%s\n' "$game_dir" > "$GAME_DIR_FILE"

    if [[ ! -f "$map_file" ]]; then
        printf 'WARNING: expected map texture was not found:\n  %s\n' \
            "$map_file" >&2
    fi

    printf 'Installed bridge plugin:\n  %s\n' "$target"
    printf 'Saved Farever directory:\n  %s\n\n' "$GAME_DIR_FILE"
    echo "Start Farever. The plugin hot-reloads automatically if the game is already running."
}

main() {
    local game_dir
    game_dir="$(resolve_game_dir "$@")"
    install_bridge "$game_dir"
}

main "$@"
