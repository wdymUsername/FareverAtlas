#!/usr/bin/env python3
"""
Farever / Heaps PAK extractor for Linux.

Project layout:

    FareverAtlas/
    ├── tools/
    │   └── farever_extractor.py
    └── extracted/

Run without a PAK path to discover the Farever Steam installation and choose
which archives to extract:

    ./farever_extractor.py --keep-dds

Explicit archives are also supported:

    ./farever_extractor.py /path/to/file.pak --keep-dds
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import BinaryIO, Iterator, Sequence


CHUNK_SIZE = 4 * 1024 * 1024
PROJECT_DIRECTORY_NAME = "FareverAtlas"
GAME_NAME_TOKEN = "farever"


class PakError(RuntimeError):
    """Raised when discovery, parsing, conversion, or extraction fails."""


@dataclass
class PakEntry:
    name: str
    is_directory: bool
    children: list["PakEntry"] = field(default_factory=list)
    position: int = 0
    size: int = 0
    checksum: int = 0


@dataclass
class PakArchive:
    version: int
    header_size: int
    data_size: int
    file_size: int
    root: PakEntry


@dataclass
class ExtractionStats:
    files: int = 0
    bytes_extracted: int = 0
    png_payloads: int = 0
    dds_payloads: int = 0
    dds_converted: int = 0
    dds_retained: int = 0
    conversion_failures: int = 0


class HeaderReader:
    def __init__(self, data: bytes):
        self.data = data
        self.position = 0

    def read(self, size: int) -> bytes:
        if size < 0:
            raise PakError(f"Invalid read size: {size}")

        end = self.position + size

        if end > len(self.data):
            raise PakError("Unexpected end of PAK header")

        result = self.data[self.position:end]
        self.position = end

        return result

    def read_byte(self) -> int:
        return self.read(1)[0]

    def read_int32(self) -> int:
        return struct.unpack("<i", self.read(4))[0]

    def read_double(self) -> float:
        return struct.unpack("<d", self.read(8))[0]

    def read_string(self) -> str:
        length = self.read_byte()

        try:
            return self.read(length).decode("utf-8")
        except UnicodeDecodeError as error:
            raise PakError(
                "Invalid UTF-8 filename in PAK header"
            ) from error


def find_project_root() -> Path:
    """
    Find FareverAtlas from the script's own physical location.
    """

    script_path = Path(__file__).resolve()

    for directory in (
        script_path.parent,
        *script_path.parents,
    ):
        if (
            directory.name.casefold()
            == PROJECT_DIRECTORY_NAME.casefold()
        ):
            return directory

    raise PakError(
        f"Could not locate the {PROJECT_DIRECTORY_NAME!r} "
        f"project root above:\n{script_path}"
    )


def unique_existing_paths(
    paths: Sequence[Path],
) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()

    for path in paths:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue

        if resolved in seen:
            continue

        if not resolved.exists():
            continue

        seen.add(resolved)
        result.append(resolved)

    return result


def known_steam_roots() -> list[Path]:
    home = Path.home()

    candidates = [
        home / ".steam" / "steam",
        home / ".local" / "share" / "Steam",
        (
            home
            / ".var"
            / "app"
            / "com.valvesoftware.Steam"
            / ".local"
            / "share"
            / "Steam"
        ),
        (
            home
            / ".var"
            / "app"
            / "com.valvesoftware.Steam"
            / "data"
            / "Steam"
        ),
    ]

    for variable in (
        "STEAM_ROOT",
        "STEAM_DIR",
    ):
        value = os.environ.get(variable)

        if value:
            candidates.insert(
                0,
                Path(value),
            )

    return unique_existing_paths(candidates)


def parse_vdf_quoted_value(
    text: str,
    key: str,
) -> list[str]:
    pattern = re.compile(
        rf'"{re.escape(key)}"\s*'
        rf'"((?:\\.|[^"\\])*)"',
        re.IGNORECASE,
    )

    values: list[str] = []

    for match in pattern.finditer(text):
        value = match.group(1)

        value = (
            value
            .replace(r"\\", "\\")
            .replace(r"\"", '"')
        )

        values.append(value)

    return values


def read_text_lossy(path: Path) -> str:
    try:
        return path.read_text(
            encoding="utf-8",
            errors="replace",
        )
    except OSError:
        return ""


def steamapps_from_library_vdf(
    steam_root: Path,
) -> list[Path]:
    candidates = [
        (
            steam_root
            / "steamapps"
            / "libraryfolders.vdf"
        ),
        (
            steam_root
            / "config"
            / "libraryfolders.vdf"
        ),
    ]

    result: list[Path] = []

    for vdf_path in candidates:
        if not vdf_path.is_file():
            continue

        text = read_text_lossy(vdf_path)

        for value in parse_vdf_quoted_value(
            text,
            "path",
        ):
            library_root = (
                Path(value)
                .expanduser()
            )

            result.append(
                library_root / "steamapps"
            )

    return result


def standard_steamapps_directories() -> list[Path]:
    candidates: list[Path] = []

    for steam_root in known_steam_roots():
        candidates.append(
            steam_root / "steamapps"
        )

        candidates.extend(
            steamapps_from_library_vdf(
                steam_root
            )
        )

    return unique_existing_paths(candidates)


def bounded_find_steamapps(
    search_root: Path,
    max_depth: int = 5,
) -> list[Path]:
    """
    Fallback search for custom Steam libraries that are absent
    from libraryfolders.vdf.
    """

    if not search_root.is_dir():
        return []

    search_root = search_root.resolve()
    result: list[Path] = []

    for current, directories, _files in os.walk(
        search_root,
        topdown=True,
        onerror=lambda _error: None,
    ):
        current_path = Path(current)

        try:
            depth = len(
                current_path
                .relative_to(search_root)
                .parts
            )
        except ValueError:
            continue

        directories[:] = [
            name
            for name in directories
            if name not in {
                ".git",
                ".cache",
                "node_modules",
                "lost+found",
            }
        ]

        if (
            current_path.name.casefold()
            == "steamapps"
        ):
            result.append(current_path)
            directories[:] = []
            continue

        if depth >= max_depth:
            directories[:] = []

    return result


def fallback_steamapps_directories() -> list[Path]:
    home = Path.home()

    user = os.environ.get(
        "USER",
        home.name,
    )

    search_roots = [
        home / "Games",
        Path("/mnt"),
        Path("/media"),
        Path("/run/media") / user,
    ]

    found: list[Path] = []

    for root in search_roots:
        found.extend(
            bounded_find_steamapps(root)
        )

    return unique_existing_paths(found)


def parse_appmanifest(
    path: Path,
) -> tuple[str, str]:
    text = read_text_lossy(path)

    names = parse_vdf_quoted_value(
        text,
        "name",
    )

    install_dirs = parse_vdf_quoted_value(
        text,
        "installdir",
    )

    name = names[0] if names else ""

    install_dir = (
        install_dirs[0]
        if install_dirs
        else ""
    )

    return name, install_dir


def game_directories_from_steamapps(
    steamapps_dirs: Sequence[Path],
) -> list[Path]:
    candidates: list[Path] = []

    for steamapps in steamapps_dirs:
        common = steamapps / "common"

        try:
            manifests = sorted(
                steamapps.glob(
                    "appmanifest_*.acf"
                )
            )
        except OSError:
            manifests = []

        for manifest in manifests:
            name, install_dir = (
                parse_appmanifest(manifest)
            )

            identity = (
                f"{name} {install_dir}"
                .casefold()
            )

            if (
                GAME_NAME_TOKEN
                not in identity
            ):
                continue

            if not install_dir:
                continue

            candidates.append(
                common / install_dir
            )

        if common.is_dir():
            try:
                for directory in common.iterdir():
                    if not directory.is_dir():
                        continue

                    if (
                        GAME_NAME_TOKEN
                        in directory.name.casefold()
                    ):
                        candidates.append(
                            directory
                        )
            except OSError:
                pass

    return unique_existing_paths(candidates)


def discover_farever_game_directories(
    explicit_game_dir: Path | None,
) -> list[Path]:
    if explicit_game_dir is not None:
        game_dir = (
            explicit_game_dir
            .expanduser()
            .resolve()
        )

        if not game_dir.is_dir():
            raise PakError(
                f"Game directory not found:\n"
                f"{game_dir}"
            )

        return [game_dir]

    steamapps = (
        standard_steamapps_directories()
    )

    game_dirs = (
        game_directories_from_steamapps(
            steamapps
        )
    )

    if game_dirs:
        return game_dirs

    fallback = (
        fallback_steamapps_directories()
    )

    steamapps = unique_existing_paths(
        [
            *steamapps,
            *fallback,
        ]
    )

    return game_directories_from_steamapps(
        steamapps
    )


def discover_pak_files(
    game_dirs: Sequence[Path],
) -> list[Path]:
    found: list[Path] = []

    for game_dir in game_dirs:
        for current, directories, files in os.walk(
            game_dir,
            topdown=True,
            onerror=lambda _error: None,
        ):
            directories[:] = [
                name
                for name in directories
                if name not in {
                    ".git",
                    "__pycache__",
                }
            ]

            current_path = Path(current)

            for filename in files:
                if (
                    Path(filename)
                    .suffix
                    .casefold()
                    != ".pak"
                ):
                    continue

                found.append(
                    (
                        current_path
                        / filename
                    ).resolve()
                )

    return sorted(
        set(found),
        key=lambda path: str(path).casefold(),
    )


def format_size(size: int) -> str:
    units = (
        "B",
        "KiB",
        "MiB",
        "GiB",
        "TiB",
    )

    value = float(size)

    for unit in units:
        if (
            value < 1024.0
            or unit == units[-1]
        ):
            if unit == "B":
                return f"{int(value)} {unit}"

            return f"{value:.1f} {unit}"

        value /= 1024.0

    return f"{size} B"


def display_discovered_paks(
    paks: Sequence[Path],
    game_dirs: Sequence[Path],
) -> None:
    print()
    print(
        "Discovered Farever PAK archives:"
    )
    print()

    for index, pak in enumerate(
        paks,
        start=1,
    ):
        relative_display = str(pak)

        for game_dir in game_dirs:
            try:
                relative_display = str(
                    pak.relative_to(game_dir)
                )

                break
            except ValueError:
                continue

        try:
            size = format_size(
                pak.stat().st_size
            )
        except OSError:
            size = "unknown size"

        print(
            f"  {index:>2}. "
            f"{relative_display}  "
            f"[{size}]"
        )


def parse_selection(
    text: str,
    count: int,
) -> list[int]:
    normalized = (
        text
        .strip()
        .casefold()
    )

    if normalized in {
        "a",
        "all",
        "*",
    }:
        return list(range(count))

    selected: set[int] = set()

    for token in normalized.split(","):
        token = token.strip()

        if not token:
            continue

        if "-" in token:
            start_text, end_text = (
                token.split("-", 1)
            )

            try:
                start = int(start_text)
                end = int(end_text)
            except ValueError as error:
                raise PakError(
                    f"Invalid selection range: "
                    f"{token!r}"
                ) from error

            if start > end:
                start, end = end, start

            for value in range(
                start,
                end + 1,
            ):
                if (
                    value < 1
                    or value > count
                ):
                    raise PakError(
                        f"Selection out of range: "
                        f"{value}"
                    )

                selected.add(value - 1)

            continue

        try:
            value = int(token)
        except ValueError as error:
            raise PakError(
                f"Invalid selection: {token!r}"
            ) from error

        if (
            value < 1
            or value > count
        ):
            raise PakError(
                f"Selection out of range: "
                f"{value}"
            )

        selected.add(value - 1)

    if not selected:
        raise PakError(
            "No PAK archives selected"
        )

    return sorted(selected)


def choose_paks_interactively(
    paks: Sequence[Path],
) -> list[Path]:
    if not sys.stdin.isatty():
        raise PakError(
            "Multiple PAK archives were found, "
            "but no interactive terminal is "
            "available. Run again with "
            "--all-paks or provide explicit "
            "PAK paths."
        )

    print()
    print("Choose archives to extract:")
    print("  one:        2")
    print("  several:    1,3,5")
    print("  range:      2-4")
    print("  everything: a")
    print("  cancel:     q")

    while True:
        try:
            response = input(
                "Selection: "
            ).strip()
        except EOFError as error:
            raise PakError(
                "Selection cancelled"
            ) from error

        if response.casefold() in {
            "q",
            "quit",
            "exit",
        }:
            raise PakError(
                "Selection cancelled"
            )

        try:
            indices = parse_selection(
                response,
                len(paks),
            )

            return [
                paks[index]
                for index in indices
            ]
        except PakError as error:
            print(
                f"Invalid selection: {error}",
                file=sys.stderr,
            )


def select_discovered_paks(
    paks: Sequence[Path],
    game_dirs: Sequence[Path],
    select_all: bool,
    list_only: bool,
) -> list[Path]:
    if not paks:
        locations = "\n".join(
            f"  - {path}"
            for path in game_dirs
        )

        raise PakError(
            "Farever was found, but no .pak "
            "files were discovered under:\n"
            f"{locations}"
        )

    display_discovered_paks(
        paks,
        game_dirs,
    )

    if list_only:
        return []

    if select_all:
        return list(paks)

    if len(paks) == 1:
        return list(paks)

    return choose_paks_interactively(
        paks
    )


def read_exact(
    stream: BinaryIO,
    size: int,
) -> bytes:
    data = stream.read(size)

    if len(data) != size:
        raise PakError(
            f"Unexpected end of file: "
            f"expected {size} bytes, "
            f"received {len(data)}"
        )

    return data


def read_entry(
    reader: HeaderReader,
) -> PakEntry:
    name = reader.read_string()
    flags = reader.read_byte()

    if flags & 1:
        child_count = reader.read_int32()

        if child_count < 0:
            raise PakError(
                f"Invalid child count for "
                f"directory {name!r}: "
                f"{child_count}"
            )

        return PakEntry(
            name=name,
            is_directory=True,
            children=[
                read_entry(reader)
                for _ in range(child_count)
            ],
        )

    if flags & 2:
        raw_position = (
            reader.read_double()
        )

        if not raw_position.is_integer():
            raise PakError(
                f"Non-integral file offset "
                f"for {name!r}: "
                f"{raw_position}"
            )

        position = int(raw_position)
    else:
        position = reader.read_int32()

    size = reader.read_int32()
    checksum = reader.read_int32()

    if position < 0:
        raise PakError(
            f"Negative file offset for "
            f"{name!r}: {position}"
        )

    if size < 0:
        raise PakError(
            f"Negative file size for "
            f"{name!r}: {size}"
        )

    return PakEntry(
        name=name,
        is_directory=False,
        position=position,
        size=size,
        checksum=checksum,
    )


def validate_entry(
    entry: PakEntry,
    available_data_size: int,
) -> int:
    """
    Validate entries against the physical bytes available after the header.

    Some Farever PAKs declare a DATA size slightly smaller than the final
    indexed entry. The physical file boundary is therefore used as the
    authoritative extraction limit.
    """

    if entry.is_directory:
        maximum_end = 0

        for child in entry.children:
            maximum_end = max(
                maximum_end,
                validate_entry(
                    child,
                    available_data_size,
                ),
            )

        return maximum_end

    end_position = entry.position + entry.size

    if end_position > available_data_size:
        raise PakError(
            f"File {entry.name!r} extends beyond "
            f"the physical PAK data: "
            f"{end_position} > {available_data_size}"
        )

    return end_position

def read_archive(
    pak_path: Path,
) -> PakArchive:
    file_size = (
        pak_path.stat().st_size
    )

    with pak_path.open("rb") as stream:
        fixed_header = read_exact(
            stream,
            12,
        )

        if fixed_header[:3] != b"PAK":
            raise PakError(
                f"Not a Heaps PAK archive:\n"
                f"{pak_path}"
            )

        version = fixed_header[3]

        header_size, data_size = (
            struct.unpack(
                "<ii",
                fixed_header[4:12],
            )
        )

        if header_size < 16:
            raise PakError(
                f"Invalid header size: "
                f"{header_size}"
            )

        if data_size < 0:
            raise PakError(
                f"Invalid data size: "
                f"{data_size}"
            )

        tree_data = read_exact(
            stream,
            header_size - 16,
        )

        reader = HeaderReader(
            tree_data
        )

        root = read_entry(reader)

        remaining_header = tree_data[
            reader.position:
        ]

        if any(remaining_header):
            raise PakError(
                "Unexpected non-zero data "
                "after the PAK directory tree"
            )

        marker = read_exact(
            stream,
            4,
        )

        if marker != b"DATA":
            raise PakError(
                f"Missing DATA marker at "
                f"offset "
                f"0x{header_size - 4:x}"
            )

    minimum_file_size = (
        header_size
        + data_size
    )

    if file_size < minimum_file_size:
        raise PakError(
            f"PAK is truncated: actual size "
            f"{file_size}, expected at least "
            f"{minimum_file_size}"
        )

    available_data_size = file_size - header_size

    maximum_entry_end = validate_entry(
        root,
        available_data_size,
    )

    if maximum_entry_end > data_size:
        print(
            "WARNING: Indexed PAK content exceeds "
            f"the declared DATA size by "
            f"{maximum_entry_end - data_size} bytes; "
            "using the physical file boundary.",
            file=sys.stderr,
        )

    return PakArchive(
        version=version,
        header_size=header_size,
        data_size=data_size,
        file_size=file_size,
        root=root,
    )


def safe_entry_name(
    name: str,
) -> str:
    if (
        not name
        or name in {".", ".."}
    ):
        raise PakError(
            f"Unsafe archive entry name: "
            f"{name!r}"
        )

    if (
        "/" in name
        or "\\" in name
        or "\0" in name
    ):
        raise PakError(
            f"Unsafe archive entry name: "
            f"{name!r}"
        )

    return name


def walk_entries(
    entry: PakEntry,
    parent: Path = Path(),
    is_root: bool = True,
) -> Iterator[
    tuple[Path, PakEntry]
]:
    if (
        is_root
        and entry.is_directory
        and entry.name == ""
    ):
        current_path = parent
    else:
        current_path = (
            parent
            / safe_entry_name(entry.name)
        )

    if entry.is_directory:
        for child in entry.children:
            yield from walk_entries(
                child,
                current_path,
                False,
            )

        return

    yield current_path, entry


def ensure_inside_output(
    output_root: Path,
    destination: Path,
) -> Path:
    resolved_root = (
        output_root.resolve()
    )

    resolved_destination = (
        destination.resolve()
    )

    try:
        resolved_destination.relative_to(
            resolved_root
        )
    except ValueError as error:
        raise PakError(
            f"Archive path escapes output "
            f"directory: {destination}"
        ) from error

    return resolved_destination


def copy_payload(
    source: BinaryIO,
    destination: Path,
    source_position: int,
    size: int,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    source.seek(source_position)
    remaining = size

    with destination.open("wb") as output:
        while remaining > 0:
            chunk = source.read(
                min(
                    CHUNK_SIZE,
                    remaining,
                )
            )

            if not chunk:
                raise PakError(
                    f"Unexpected EOF while "
                    f"extracting:\n"
                    f"{destination}"
                )

            output.write(chunk)
            remaining -= len(chunk)


def detect_converters() -> list[str]:
    return [
        converter
        for converter in (
            "magick",
            "convert",
            "ffmpeg",
        )
        if shutil.which(converter)
    ]


def build_conversion_command(
    converter: str,
    dds_path: Path,
    png_path: Path,
) -> list[str]:
    if converter == "magick":
        return [
            "magick",
            f"{dds_path}[0]",
            str(png_path),
        ]

    if converter == "convert":
        return [
            "convert",
            f"{dds_path}[0]",
            str(png_path),
        ]

    if converter == "ffmpeg":
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(dds_path),
            "-frames:v",
            "1",
            str(png_path),
        ]

    raise PakError(
        f"Unsupported converter: "
        f"{converter}"
    )


def convert_dds(
    converters: Sequence[str],
    dds_path: Path,
    png_path: Path,
) -> str:
    errors: list[str] = []

    for converter in converters:
        result = subprocess.run(
            build_conversion_command(
                converter,
                dds_path,
                png_path,
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        if (
            result.returncode == 0
            and png_path.is_file()
            and png_path.stat().st_size > 0
        ):
            return converter

        if png_path.exists():
            png_path.unlink()

        message = (
            result.stderr
            or result.stdout
            or "unknown conversion error"
        ).strip()

        errors.append(
            f"{converter}: {message}"
        )

    raise PakError(
        "\n".join(errors)
    )


def list_archive(
    archive: PakArchive,
) -> None:
    print()

    print(
        f"{'SIZE':>12}  "
        f"{'DATA OFFSET':>14}  "
        f"PATH"
    )

    print(
        f"{'-' * 12}  "
        f"{'-' * 14}  "
        f"{'-' * 40}"
    )

    for relative_path, entry in walk_entries(
        archive.root
    ):
        print(
            f"{entry.size:12d}  "
            f"0x{entry.position:012x}  "
            f"{relative_path}"
        )


def extract_archive(
    pak_path: Path,
    archive: PakArchive,
    output_directory: Path,
    convert_textures: bool,
    keep_dds: bool,
) -> ExtractionStats:
    stats = ExtractionStats()

    converters = (
        detect_converters()
        if convert_textures
        else []
    )

    if convert_textures:
        if converters:
            print(
                "DDS converters: "
                + ", ".join(converters)
            )
        else:
            print(
                "WARNING: ImageMagick and "
                "FFmpeg were not found; "
                "DDS files will be retained.",
                file=sys.stderr,
            )
    else:
        print(
            "DDS conversion disabled."
        )

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    with pak_path.open("rb") as source:
        for relative_path, entry in walk_entries(
            archive.root
        ):
            stats.files += 1

            stats.bytes_extracted += (
                entry.size
            )

            source_position = (
                archive.header_size
                + entry.position
            )

            source.seek(source_position)
            magic = source.read(4)

            destination = ensure_inside_output(
                output_directory,
                output_directory
                / relative_path,
            )

            if magic == b"DDS ":
                stats.dds_payloads += 1

                dds_path = ensure_inside_output(
                    output_directory,
                    destination.with_suffix(
                        ".dds"
                    ),
                )

                png_path = ensure_inside_output(
                    output_directory,
                    destination.with_suffix(
                        ".png"
                    ),
                )

                copy_payload(
                    source,
                    dds_path,
                    source_position,
                    entry.size,
                )

                if not converters:
                    stats.dds_retained += 1

                    print(
                        f"DDS   {relative_path} "
                        f"-> "
                        f"{dds_path.relative_to(output_directory)}"
                    )

                    continue

                try:
                    converter = convert_dds(
                        converters,
                        dds_path,
                        png_path,
                    )

                    stats.dds_converted += 1

                    print(
                        f"DDS   {relative_path} "
                        f"-> "
                        f"{png_path.relative_to(output_directory)} "
                        f"[{converter}]"
                    )

                    if keep_dds:
                        stats.dds_retained += 1
                    else:
                        dds_path.unlink()

                except PakError as error:
                    stats.conversion_failures += 1
                    stats.dds_retained += 1

                    print(
                        f"WARNING: DDS conversion "
                        f"failed for "
                        f"{relative_path}; retained "
                        f"{dds_path.relative_to(output_directory)}",
                        file=sys.stderr,
                    )

                    print(
                        str(error),
                        file=sys.stderr,
                    )

                continue

            if magic == b"\x89PNG":
                stats.png_payloads += 1
                file_type = "PNG"
            else:
                file_type = "FILE"

            copy_payload(
                source,
                destination,
                source_position,
                entry.size,
            )

            print(
                f"{file_type:<5} "
                f"{relative_path}"
            )

    return stats


def safe_output_component(
    value: str,
) -> str:
    cleaned = re.sub(
        r"[^A-Za-z0-9._-]+",
        "_",
        value,
    ).strip("._")

    return cleaned or "archive"


def default_output_directories(
    project_root: Path,
    paks: Sequence[Path],
    output_override: Path | None,
) -> dict[Path, Path]:
    result: dict[Path, Path] = {}
    used: set[Path] = set()

    if output_override is not None:
        override = (
            output_override
            .expanduser()
            .resolve()
        )

        if len(paks) == 1:
            return {
                paks[0]: override
            }

        base_root = override
    else:
        base_root = (
            project_root
            / "extracted"
        )

    for pak in paks:
        candidate = (
            base_root
            / safe_output_component(
                pak.stem
            )
        )

        if candidate in used:
            candidate = (
                base_root
                / safe_output_component(
                    f"{pak.parent.name}"
                    f"__{pak.stem}"
                )
            )

        suffix = 2
        original = candidate

        while candidate in used:
            candidate = original.with_name(
                f"{original.name}_{suffix}"
            )

            suffix += 1

        used.add(candidate)
        result[pak] = candidate

    return result


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Discover and extract Farever "
            "Heaps hxd.fmt.pak archives. "
            "When no PAK path is supplied, "
            "Steam libraries are searched "
            "automatically and an archive "
            "selection menu is shown."
        )
    )

    parser.add_argument(
        "pak",
        nargs="*",
        type=Path,
        help=(
            "Optional explicit PAK "
            "file path(s)"
        ),
    )

    parser.add_argument(
        "--game-dir",
        type=Path,
        help=(
            "Search this Farever game "
            "directory instead of Steam "
            "discovery"
        ),
    )

    parser.add_argument(
        "--all-paks",
        action="store_true",
        help=(
            "Extract every discovered PAK "
            "without prompting"
        ),
    )

    parser.add_argument(
        "--list-paks",
        action="store_true",
        help=(
            "Discover and list PAK files, "
            "then exit"
        ),
    )

    parser.add_argument(
        "-o",
        "--out",
        type=Path,
        help=(
            "Output directory. For multiple "
            "PAKs this becomes the parent "
            "directory for one subdirectory "
            "per archive."
        ),
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help=(
            "List archive contents without "
            "extracting"
        ),
    )

    parser.add_argument(
        "--no-convert",
        action="store_true",
        help=(
            "Do not convert DDS textures "
            "to PNG"
        ),
    )

    parser.add_argument(
        "--keep-dds",
        action="store_true",
        help=(
            "Keep original DDS files after "
            "successful PNG conversion"
        ),
    )

    return parser.parse_args()


def resolve_selected_paks(
    arguments: argparse.Namespace,
) -> list[Path]:
    if arguments.pak:
        selected: list[Path] = []

        for value in arguments.pak:
            pak = (
                value
                .expanduser()
                .resolve()
            )

            if not pak.is_file():
                raise PakError(
                    f"PAK file not found:\n"
                    f"{pak}"
                )

            selected.append(pak)

        return selected

    game_dirs = (
        discover_farever_game_directories(
            arguments.game_dir
        )
    )

    if not game_dirs:
        raise PakError(
            "Could not find a Farever "
            "installation. Steam library "
            "metadata and common custom "
            "library locations were searched. "
            "Use --game-dir to point directly "
            "at the game folder."
        )

    print(
        "Farever installation(s):"
    )

    for directory in game_dirs:
        print(
            f"  - {directory}"
        )

    discovered = discover_pak_files(
        game_dirs
    )

    return select_discovered_paks(
        discovered,
        game_dirs,
        select_all=arguments.all_paks,
        list_only=arguments.list_paks,
    )


def print_archive_summary(
    pak_path: Path,
    archive: PakArchive,
) -> None:
    print(
        f"PAK:          {pak_path}"
    )

    print(
        f"Version:      "
        f"{archive.version}"
    )

    print(
        f"Header size:  "
        f"{archive.header_size}"
    )

    print(
        f"Data size:    "
        f"{archive.data_size}"
    )

    print(
        f"File size:    "
        f"{archive.file_size}"
    )


def print_extraction_summary(
    stats: ExtractionStats,
) -> None:
    print(
        "Extraction complete."
    )

    print(
        f"Files extracted:     "
        f"{stats.files}"
    )

    print(
        f"Payload bytes:       "
        f"{stats.bytes_extracted}"
    )

    print(
        f"PNG payloads:        "
        f"{stats.png_payloads}"
    )

    print(
        f"DDS payloads:        "
        f"{stats.dds_payloads}"
    )

    print(
        f"DDS converted:       "
        f"{stats.dds_converted}"
    )

    print(
        f"DDS retained:        "
        f"{stats.dds_retained}"
    )

    print(
        f"Conversion failures: "
        f"{stats.conversion_failures}"
    )


def main() -> int:
    arguments = parse_arguments()

    project_root = find_project_root()

    selected_paks = resolve_selected_paks(
        arguments
    )

    if (
        arguments.list_paks
        and not arguments.pak
    ):
        return 0

    if not selected_paks:
        raise PakError(
            "No PAK archives selected"
        )

    output_directories = (
        default_output_directories(
            project_root,
            selected_paks,
            arguments.out,
        )
    )

    print()

    print(
        f"Project root: "
        f"{project_root}"
    )

    for index, pak_path in enumerate(
        selected_paks,
        start=1,
    ):
        if len(selected_paks) > 1:
            print()

            print(
                f"=== Archive "
                f"{index}/"
                f"{len(selected_paks)} ==="
            )

        archive = read_archive(
            pak_path
        )

        print_archive_summary(
            pak_path,
            archive,
        )

        if arguments.list:
            list_archive(archive)
            continue

        output_directory = (
            output_directories[pak_path]
        )

        print(
            f"Output:       "
            f"{output_directory}"
        )

        stats = extract_archive(
            pak_path=pak_path,
            archive=archive,
            output_directory=output_directory,
            convert_textures=(
                not arguments.no_convert
            ),
            keep_dds=arguments.keep_dds,
        )

        print()

        print_extraction_summary(
            stats
        )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(
            main()
        )

    except (
        PakError,
        OSError,
        UnicodeError,
    ) as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )

        raise SystemExit(1)