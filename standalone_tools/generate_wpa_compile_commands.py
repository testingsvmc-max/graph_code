#!/usr/bin/env python3
"""
Emit a compile_commands.json for the Android tree layout:
  <root>/wpa_supplicant/*.c and subdirs

Uses the same -I layout as wpa_supplicant/Android.mk (LOCAL_PATH + src/...).
Parses defconfig for uncommented CONFIG_*=y|m lines as -D flags.

Usage:
  python standalone_tools/generate_wpa_compile_commands.py [path/to/android-wpa_supplicant-inner]

Default CC is clang; override with CC=gcc in the environment if needed.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Include dirs relative to wpa_supplicant/ (from Android.mk INCLUDES)
REL_INCLUDES = [
    ".",
    "src",
    "src/common",
    "src/drivers",
    "src/eap_common",
    "src/eapol_supp",
    "src/eap_peer",
    "src/eap_server",
    "src/hlr_auc_gw",
    "src/l2_packet",
    "src/radius",
    "src/rsn_supp",
    "src/tls",
    "src/utils",
    "src/wps",
    "src/ap",
    "src/p2p",
    "src/fst",
]

EXTRA_DEFINES = [
    "-DWPA_IGNORE_CONFIG_ERRORS",
    "-DWPA_UNICODE_SSID",
    "-DOPENSSL_NO_ENGINE",
    "-D_GNU_SOURCE",
]


def parse_defconfig(defconfig: Path) -> list[str]:
    flags: list[str] = []
    if not defconfig.is_file():
        return flags
    cfg_re = re.compile(r"^\s*(CONFIG_[A-Za-z0-9_]+)=(y|m)\s*$")
    for line in defconfig.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = cfg_re.match(s)
        if m:
            flags.append(f"-D{m.group(1)}=1")
    return flags


def resolve_project_root(arg: Path) -> Path:
    arg = arg.resolve()
    if (arg / "wpa_supplicant").is_dir():
        return arg
    nested = arg / "android-wpa_supplicant-master"
    if (nested / "wpa_supplicant").is_dir():
        return nested
    return arg


def main() -> int:
    default = Path(r"D:\GraphCode\android-wpa_supplicant-master")
    root = resolve_project_root(Path(sys.argv[1]) if len(sys.argv) > 1 else default)
    wpa = root / "wpa_supplicant"
    if not wpa.is_dir():
        print(f"Not found: {wpa} (pass inner tree root that contains wpa_supplicant/)", file=sys.stderr)
        return 1

    cc = os.environ.get("CC", "clang")
    def_flags = parse_defconfig(wpa / "defconfig")
    i_flags: list[str] = []
    for rel in REL_INCLUDES:
        p = wpa / rel
        if rel == "." or p.is_dir():
            i_flags.append("-I" + str((wpa / rel).resolve()))

    entries: list[dict] = []
    for cfile in sorted(wpa.rglob("*.c")):
        rel = cfile.relative_to(wpa)
        # Skip huge or test-only trees if desired; keep all for completeness
        args = [cc, "-std=gnu11", "-c", str(rel), *i_flags, *EXTRA_DEFINES, *def_flags]
        entries.append({"directory": str(wpa).replace("\\", "/"), "file": str(rel).replace("\\", "/"), "arguments": args})

    out = wpa / "compile_commands.json"
    out.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    print(f"Wrote {len(entries)} entries to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
