"""Resolve and apply the UI font (Noto Sans) on Linux and Windows.

Prefer a system install, then a bundled copy under assets/fonts/. If neither
is available, download the Google Fonts variable Noto Sans (SIL OFL) into the
project assets tree so packaging and portable builds stay consistent.
"""

from __future__ import annotations

import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

UI_FONT_FAMILY = "Noto Sans"
VARIABLE_FONT_NAME = "NotoSans-Variable.ttf"
STATIC_FACE_NAMES = (
    "NotoSans-Regular.ttf",
    "NotoSans-Medium.ttf",
    "NotoSans-SemiBold.ttf",
    "NotoSans-Bold.ttf",
)
OFL_NAME = "OFL.txt"

# raw.githubusercontent.com works with urllib on Linux and Windows (no auth).
_FONT_DOWNLOAD_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/"
    "NotoSans%5Bwdth%2Cwght%5D.ttf"
)
_OFL_DOWNLOAD_URL = (
    "https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/OFL.txt"
)
_USER_AGENT = "FareverAtlas/1.0 (+https://github.com/)"


def project_fonts_dir() -> Path:
    """Writable/source-tree fonts directory used by setup and packaging."""
    from .config import PROJECT_ROOT

    return PROJECT_ROOT / "assets" / "fonts"


def bundled_fonts_dir() -> Path:
    """Fonts directory visible at runtime (PyInstaller extract dir when frozen)."""
    from .config import ASSET_ROOT

    return ASSET_ROOT / "fonts"


def _has_variable_font(directory: Path) -> bool:
    return (directory / VARIABLE_FONT_NAME).is_file()


def _has_static_faces(directory: Path) -> bool:
    return all((directory / name).is_file() for name in STATIC_FACE_NAMES)


def fonts_ready(directory: Path | None = None) -> bool:
    directory = directory or project_fonts_dir()
    return _has_variable_font(directory) or _has_static_faces(directory)


def _iter_system_font_roots() -> list[Path]:
    roots: list[Path] = []
    windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot")
    if windir:
        roots.append(Path(windir) / "Fonts")
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        roots.append(Path(local_app) / "Microsoft" / "Windows" / "Fonts")
    roots.extend(
        [
            Path("/usr/share/fonts/google-noto"),
            Path("/usr/share/fonts/noto"),
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path.home() / ".local" / "share" / "fonts",
            Path.home() / ".fonts",
        ]
    )
    return roots


def _fc_list_noto_files() -> list[Path]:
    if os.name == "nt":
        return []
    try:
        import subprocess

        completed = subprocess.run(
            ["fc-list", ":family=Noto Sans", "file"],
            check=False,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, OSError):
        return []
    found: list[Path] = []
    for line in completed.stdout.splitlines():
        path_text = line.split(":", 1)[0].strip()
        if not path_text:
            continue
        path = Path(path_text)
        if path.is_file():
            found.append(path)
    return found


def _is_noto_sans_variable_roman(path: Path) -> bool:
    name = path.name.lower()
    if not name.startswith("notosans"):
        return False
    if "italic" in name:
        return False
    if name == VARIABLE_FONT_NAME.lower() or "variable" in name:
        return True
    # Google/system VF names look like NotoSans[wght].ttf or NotoSans[wdth,wght].ttf
    return "[" in name and "wght" in name


def _find_system_variable_font() -> Path | None:
    for path in _fc_list_noto_files():
        if _is_noto_sans_variable_roman(path):
            return path
    for root in _iter_system_font_roots():
        if not root.is_dir():
            continue
        for path in root.rglob("*.ttf"):
            if _is_noto_sans_variable_roman(path):
                return path
    return None


def _find_system_static_faces() -> dict[str, Path]:
    wanted = {name.lower(): name for name in STATIC_FACE_NAMES}
    found: dict[str, Path] = {}
    candidates = list(_fc_list_noto_files())
    for root in _iter_system_font_roots():
        if not root.is_dir():
            continue
        for name in STATIC_FACE_NAMES:
            candidate = root / name
            if candidate.is_file():
                candidates.append(candidate)
            # Common nested layout: .../NotoSans/NotoSans-Regular.ttf
            nested = root / "NotoSans" / name
            if nested.is_file():
                candidates.append(nested)
    for path in candidates:
        key = path.name.lower()
        if key in wanted and wanted[key] not in found:
            found[wanted[key]] = path
    return found


def _copy_file(source: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to download {url}: {exc}") from exc
    if len(data) < 1024:
        raise RuntimeError(f"Download from {url} looked too small ({len(data)} bytes)")
    partial.write_bytes(data)
    partial.replace(dest)


def _ensure_ofl(directory: Path, *, allow_download: bool) -> None:
    dest = directory / OFL_NAME
    if dest.is_file():
        return
    for root in _iter_system_font_roots():
        for candidate in (
            root / OFL_NAME,
            root.parent / "licenses" / "google-noto-fonts-common" / "LICENSE",
        ):
            if candidate.is_file():
                _copy_file(candidate, dest)
                return
    system_license = Path("/usr/share/licenses/google-noto-fonts-common/LICENSE")
    if system_license.is_file():
        _copy_file(system_license, dest)
        return
    if allow_download:
        _download(_OFL_DOWNLOAD_URL, dest)


def ensure_ui_fonts(
    directory: Path | None = None,
    *,
    allow_download: bool = True,
) -> Path:
    """Make sure Noto Sans files exist under assets/fonts/.

    Order: already bundled → copy from the machine → download (if allowed).
    """
    directory = directory or project_fonts_dir()
    directory.mkdir(parents=True, exist_ok=True)

    if fonts_ready(directory):
        _ensure_ofl(directory, allow_download=allow_download)
        return directory

    variable = _find_system_variable_font()
    if variable is not None:
        _copy_file(variable, directory / VARIABLE_FONT_NAME)
        _ensure_ofl(directory, allow_download=allow_download)
        return directory

    static = _find_system_static_faces()
    if len(static) == len(STATIC_FACE_NAMES):
        for name, source in static.items():
            _copy_file(source, directory / name)
        _ensure_ofl(directory, allow_download=allow_download)
        return directory

    if not allow_download:
        raise FileNotFoundError(
            f"Noto Sans not found on this machine and download disabled ({directory})"
        )

    print(f"Downloading {UI_FONT_FAMILY} into {directory} ...", file=sys.stderr)
    _download(_FONT_DOWNLOAD_URL, directory / VARIABLE_FONT_NAME)
    _ensure_ofl(directory, allow_download=True)
    if not fonts_ready(directory):
        raise RuntimeError(f"Failed to prepare UI fonts in {directory}")
    return directory


def apply_ui_font(app: object, *, point_size: int = 10) -> str | None:
    """Load bundled fonts (if any) and pin the application font when available."""
    from PySide6 import QtGui, QtWidgets

    if not isinstance(app, QtWidgets.QApplication):
        raise TypeError("apply_ui_font expects a QApplication")

    fonts_dir = bundled_fonts_dir()
    if fonts_dir.is_dir():
        for path in sorted(fonts_dir.glob("*.ttf")) + sorted(fonts_dir.glob("*.otf")):
            QtGui.QFontDatabase.addApplicationFont(str(path))

    font = app.font()
    family: str | None = None
    if UI_FONT_FAMILY in QtGui.QFontDatabase.families():
        family = UI_FONT_FAMILY
        font.setFamily(family)
    font.setPointSize(point_size)
    app.setFont(font)
    return family


def main() -> int:
    path = ensure_ui_fonts()
    print(f"UI fonts ready: {path}")
    if _has_variable_font(path):
        print(f"  {VARIABLE_FONT_NAME}")
    else:
        for name in STATIC_FACE_NAMES:
            print(f"  {name}")
    if (path / OFL_NAME).is_file():
        print(f"  {OFL_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
