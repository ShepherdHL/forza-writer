"""Best-effort auto-detection of two external install locations this app
depends on but can't bundle: a Forza Horizon 6 install (for the reference
vinyl modelbin -- see README.md's "Required asset" section) and KFPS (for
the Plates tab's "Send to KFPS" button, see gui_settings.DEFAULT_SETTINGS'
kfps_executable). Windows-only, like the rest of this project's
system-integration code (gen_modelbin_web/state.py's font registry reads).

Every lookup here is advisory, not authoritative: a miss just leaves the
Settings tab's existing manual Browse flow in place, nothing breaks. The
FH6 search deliberately doesn't hardcode an exact folder/display name --
Microsoft Store/Xbox app install names, Steam's app naming, and even which
storefronts this title ships on are all things this code can't verify --
so every strategy below casts a wide "Forza*" net and the real
confirmation is always the same one README.md tells a user to check by
hand: does media/Livery/Vinyls.zip actually exist under the candidate.
"""
from __future__ import annotations

import os
import re
import string
import subprocess
import winreg
import zipfile
from pathlib import Path

VINYL_ZIP_RELATIVE = Path("media") / "Livery" / "Vinyls.zip"
REFERENCE_MODELBIN_NAME = "S_01.modelbin"


def _dedupe(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def _steam_library_roots() -> list[Path]:
    """Every Steam library folder on this machine (main install dir plus
    any additional drives added in Steam's own Storage settings)."""
    steam_roots = []
    for hive, subkey in (
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
    ):
        try:
            with winreg.OpenKey(hive, subkey) as key:
                value, _ = winreg.QueryValueEx(key, "InstallPath")
                steam_roots.append(Path(value))
        except OSError:
            continue

    library_roots = list(steam_roots)
    for steam_root in _dedupe(steam_roots):
        vdf_path = steam_root / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in re.finditer(r'"path"\s*"([^"]+)"', text):
            library_roots.append(Path(match.group(1).replace("\\\\", "\\")))
    return _dedupe(library_roots)


def _logical_drives() -> list[Path]:
    import ctypes
    bitmask = ctypes.windll.kernel32.GetLogicalDrives()
    return [Path(f"{letter}:/") for i, letter in enumerate(string.ascii_uppercase) if bitmask & (1 << i)]


def _xbox_app_candidates() -> list[Path]:
    """The Xbox app's default per-drive install root (<drive>\\XboxGames\\
    <game>\\Content) -- the common case, since a AAA title rarely fits on
    a stock C: drive and the app lets a user pick any drive for it."""
    candidates = []
    for drive in _logical_drives():
        xbox_games = drive / "XboxGames"
        if not xbox_games.is_dir():
            continue
        try:
            entries = list(xbox_games.glob("Forza*"))
        except OSError:
            continue
        for entry in entries:
            candidates.append(entry / "Content")
            candidates.append(entry)
    return candidates


def _appx_install_candidates() -> list[Path]:
    """Install locations of any installed AppX/MSIX package whose name
    mentions Forza, via the AppX API rather than guessing a filesystem
    path -- the only reliable way to resolve a WindowsApps-based install,
    since that folder's ACLs generally block direct traversal."""
    candidates = []
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             "Get-AppxPackage | Where-Object { $_.Name -like '*Forza*' } | "
             "Select-Object -ExpandProperty InstallLocation"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return candidates
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line:
            candidates.append(Path(line))
    return candidates


def find_fh6_vinyls_zip() -> Path | None:
    """Locate Forza Horizon 6's Vinyls.zip across every install strategy
    this machine might use (Xbox app, Microsoft Store/AppX, Steam).
    Returns None if nothing panned out -- the caller falls back to the
    existing manual Browse flow. If more than one Forza title is
    installed, prefers whichever candidate's path mentions "6".
    """
    candidates: list[Path] = []
    candidates.extend(_appx_install_candidates())
    candidates.extend(_xbox_app_candidates())
    for root in _steam_library_roots():
        common = root / "steamapps" / "common"
        if not common.is_dir():
            continue
        try:
            candidates.extend(common.glob("Forza*"))
        except OSError:
            continue

    found = [root / VINYL_ZIP_RELATIVE for root in _dedupe(candidates)]
    found = [zip_path for zip_path in found if zip_path.is_file()]
    if not found:
        return None
    for zip_path in found:
        if "6" in str(zip_path.parent.parent.parent.name):
            return zip_path
    return found[0]


def extract_reference_modelbin(dest_path: Path, zip_path: Path | None = None) -> Path:
    """Extract S_01.modelbin from a located Vinyls.zip to dest_path,
    mirroring README.md's "Required asset" steps exactly. Raises
    FileNotFoundError if no zip was located/given, or the modelbin isn't
    inside it (a differently-versioned/renamed Vinyls.zip).
    """
    resolved_zip = zip_path or find_fh6_vinyls_zip()
    if resolved_zip is None:
        raise FileNotFoundError(
            "Could not locate a Forza Horizon 6 install with media/Livery/Vinyls.zip.")
    with zipfile.ZipFile(resolved_zip) as archive:
        try:
            data = archive.read(REFERENCE_MODELBIN_NAME)
        except KeyError as exc:
            raise FileNotFoundError(
                f"{REFERENCE_MODELBIN_NAME} not found inside {resolved_zip}") from exc
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_bytes(data)
    return dest_path


def find_kfps_executable() -> Path | None:
    """Best-effort search for KFPS.exe. KFPS is community software with no
    registry footprint to query authoritatively, so this only checks the
    handful of places a Windows install/portable-zip commonly ends up --
    one or two folders deep under the usual per-user/all-users program
    roots, plus Desktop/Downloads for a portable copy, plus this repo's own
    parent folder (a user who keeps FH6-modding tools together tends to
    have Forza Writer and something like a "Forza Painter"/KFPS folder as
    siblings under one shared parent -- confirmed against a real install at
    <parent>/Forza Painter/KFPS/KFPS.exe) -- rather than crawling the whole
    filesystem.
    """
    roots = [
        os.environ.get("LOCALAPPDATA"),
        os.environ.get("ProgramFiles"),
        os.environ.get("ProgramFiles(x86)"),
    ]
    home = Path.home()
    repo_parent = Path(__file__).resolve().parent.parent.parent
    shallow_roots = [Path(r) for r in roots if r]
    deep_roots = [home / "Desktop", home / "Downloads", repo_parent]

    candidates: list[Path] = []
    for root in shallow_roots:
        if not root.is_dir():
            continue
        for depth_pattern in ("KFPS.exe", "*/KFPS.exe", "*/*/KFPS.exe"):
            try:
                candidates.extend(root.glob(depth_pattern))
            except OSError:
                continue
    for root in deep_roots:
        if not root.is_dir():
            continue
        for depth_pattern in ("KFPS.exe", "*/KFPS.exe", "*/*/KFPS.exe", "*/*/*/KFPS.exe"):
            try:
                candidates.extend(root.glob(depth_pattern))
            except OSError:
                continue
    # A drive's own top level, for a manually-created e.g. D:\KFPS\KFPS.exe.
    for drive in _logical_drives():
        for depth_pattern in ("KFPS/KFPS.exe", "Games/KFPS/KFPS.exe"):
            candidate = drive / depth_pattern
            if candidate.is_file():
                candidates.append(candidate)

    valid = [c for c in _dedupe(candidates) if c.is_file()]
    # Prefer whichever candidate actually has the fabric-editor resources
    # file_preview.kfps_vinyls_dir() looks for, over just the first one
    # found. An in-place KFPS update can restructure the install one folder
    # deeper (confirmed against a real install: a stray old KFPS.exe was
    # left behind at <parent>/Forza Painter/KFPS/KFPS.exe after an update
    # moved the real, current install to
    # <parent>/Forza Painter/KFPS/KloudysFH6Painter/KFPS.exe), and nothing
    # about the filename tells the two apart. Falls back to the first
    # candidate found if none have the resources folder, rather than
    # returning nothing: this path is also used to launch KFPS from the
    # Plates tab, where a copy missing that folder can still be perfectly
    # valid.
    with_resources = [c for c in valid
                       if (c.parent / "tools" / "fabric-editor" / "Resources" / "Vinyls").is_dir()]
    if with_resources:
        return with_resources[0]
    return valid[0] if valid else None
