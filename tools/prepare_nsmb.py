#!/usr/bin/env python3
"""Prepare New Super Mario Bros. DS code images and ndsrecomp configs.

Unpacks ARM9, ARM7, and all 131 overlays from the retail ROM. Generates
the TOML manifests consumed by nds_recompile to emit static C banks.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import struct
import sys

try:
    import ndspy.codeCompression as code_compression
    import ndspy.rom
except ImportError as exc:
    raise SystemExit(
        "ndspy is required. Run using a Python environment with ndspy installed."
    ) from exc

EXPECTED_ROMS = {
    # USA / Australia (A2DE) - Primary Target
    "a22713711b5cd58dfbafc9688dadea66c59888ce": {
        "title": "New Super Mario Bros. (USA)",
        "code": b"A2DE",
        "region": "USA",
    },
    # Europe (A2DP)
    "b0f7886720e842ed922569e1bb5c39c0fa090331": {
        "title": "New Super Mario Bros. (Europe)",
        "code": b"A2DP",
        "region": "Europe",
    },
}

FUNCTION_RE = re.compile(
    r"^(?P<name>.+?) kind:function\((?P<mode>arm|thumb),size=0x"
    r"(?P<size>[0-9a-fA-F]+)\) addr:0x(?P<addr>[0-9a-fA-F]+)$"
)
SECTION_RE = re.compile(
    r"^\s*\.\S+\s+start:0x(?P<start>[0-9a-fA-F]+)\s+"
    r"end:0x(?P<end>[0-9a-fA-F]+)\s+kind:(?P<kind>\w+)"
)

DS_MAIN_RAM_LIMIT = 0x02400000


def extract_arm9_runtime(binary: bytes, load_address: int) -> tuple[int, bytes]:
    """Read the SDK autoload table, retaining only its main-RAM code copy.

    The source image is laid out before autoload. Compiling that entire image
    at a shifted base also declares unrelated bytes as runtime instructions.
    Use exactly the installed block instead; ITCM and DTCM are separate copies.
    """
    magic = struct.pack("<II", 0xDEC00621, 0x2106C0DE)
    marker = binary.find(magic)
    if marker < 28 or binary.find(magic, marker + 1) != -1:
        raise ValueError("ARM9 must contain one SDK module-parameters signature")
    table_start, table_end, source = struct.unpack_from("<III", binary, marker - 28)
    first, last = table_start - load_address, table_end - load_address
    if not (0 <= first <= last <= len(binary)) or (last - first) % 12:
        raise ValueError("Invalid ARM9 autoload table bounds")
    copies: list[tuple[int, bytes]] = []
    for offset in range(first, last, 12):
        destination, size, _bss = struct.unpack_from("<III", binary, offset)
        source_offset = source - load_address
        if not (0 <= source_offset <= len(binary)) or source_offset + size > len(binary):
            raise ValueError("ARM9 autoload source is outside the image")
        if size and 0x02000000 <= destination < DS_MAIN_RAM_LIMIT:
            if destination + size > DS_MAIN_RAM_LIMIT:
                raise ValueError("ARM9 autoload copy exceeds main RAM")
            copies.append((destination, binary[source_offset:source_offset + size]))
        source += size
    if len(copies) != 1:
        raise ValueError("Expected exactly one nonempty ARM9 main-RAM autoload copy")
    return copies[0]


def sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def sanitize_symbol_name(name: str) -> str:
    name = name.replace("~", "dtor_")
    name = name.replace("::", "_")
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    if name and name[0].isdigit():
        name = f"_{name}"
    return name


def parse_functions(path: pathlib.Path, start: int, end: int) -> list[dict[str, object]]:
    functions: list[dict[str, object]] = []
    if not path.is_file():
        return functions
    from collections import Counter
    raw_functions: list[tuple[int, int, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = FUNCTION_RE.match(line)
        if not match:
            continue
        addr = int(match.group("addr"), 16)
        size = int(match.group("size"), 16)
        if start <= addr and addr + size <= end:
            raw_functions.append(
                (addr, size, match.group("mode"), sanitize_symbol_name(match.group("name")))
            )
    counts = Counter(name for _, _, _, name in raw_functions)
    for addr, size, mode, name in raw_functions:
        final_name = f"{name}_{addr:08x}" if counts[name] > 1 else name
        functions.append(
            {
                "addr": addr,
                "size": size,
                "mode": mode,
                "name": final_name,
            }
        )
    functions.sort(key=lambda item: (int(item["addr"]), str(item["mode"])))
    return functions


def parse_data_ranges(path: pathlib.Path, start: int, end: int) -> list[tuple[int, int, str]]:
    ranges: list[tuple[int, int, str]] = []
    if not path.is_file():
        return ranges
    for line in path.read_text(encoding="utf-8").splitlines():
        match = SECTION_RE.match(line)
        if not match or match.group("kind") == "code":
            continue
        range_start = max(start, int(match.group("start"), 16))
        range_end = min(end, int(match.group("end"), 16))
        if range_start < range_end:
            ranges.append((range_start, range_end, f"decomp {match.group('kind')} section"))
    return ranges


def write_config(
    path: pathlib.Path,
    *,
    name: str,
    program_id: str,
    load_address: int,
    entry_pc: int,
    binary: bytes,
    functions: list[dict[str, object]],
    data_ranges: list[tuple[int, int, str]],
    extra_seeds_file: pathlib.Path | None = None,
    authoritative: bool = False,
) -> None:
    lines = [
        f"# AUTO-GENERATED by tools/prepare_nsmb.py; do not commit.",
        "[program]",
        f"name = {toml_string(name)}",
        f"id = {toml_string(program_id)}",
        f"load_address = 0x{load_address:08x}",
        f"size = 0x{len(binary):08x}",
        f"entry_pc = 0x{entry_pc:08x}",
        f"authoritative_entry_points = {'true' if authoritative else 'false'}",
        "",
        "[identity]",
        f"sha1 = {toml_string(sha1(binary))}",
        "",
    ]
    for function in functions:
        lines.extend(
            [
                "[[entry_point]]",
                f"addr = 0x{int(function['addr']):08x}",
                f"size = 0x{int(function['size']):x}",
                f"mode = {toml_string(str(function['mode']))}",
                f"name = {toml_string(str(function['name']))}",
                "",
            ]
        )
    for range_start, range_end, note in data_ranges:
        lines.extend(
            [
                "[[data_range]]",
                f"start = 0x{range_start:08x}",
                f"end = 0x{range_end:08x}",
                f"note = {toml_string(note)}",
                "",
            ]
        )
    content = "\n".join(lines)
    if extra_seeds_file and extra_seeds_file.is_file():
        content += "\n" + extra_seeds_file.read_text(encoding="utf-8") + "\n"
    path.write_text(content, encoding="utf-8", newline="\n")


def write_overlay_config(
    path: pathlib.Path,
    *,
    title: str,
    program_id: str,
    overlay_id: int,
    load_address: int,
    binary: bytes,
    bss_size: int,
    static_init_start: int,
    static_init_end: int,
    extra_seeds_file: pathlib.Path | None = None,
) -> None:
    lines = [
        f"# AUTO-GENERATED by tools/prepare_nsmb.py; do not commit.",
        "[program]",
        f"name = {toml_string(f'{title} ARM9 overlay {overlay_id}')}",
        f"id = {toml_string(f'{program_id}_ov{overlay_id:03d}')}",
        f"load_address = 0x{load_address:08x}",
        f"size = 0x{len(binary):08x}",
        f"entry_pc = 0x{load_address:08x}",
        "authoritative_entry_points = false",
        "",
        "[identity]",
        f"sha1 = {toml_string(sha1(binary))}",
        "",
        "[overlay]",
        f"id = {overlay_id}",
        f"bss_size = 0x{bss_size:08x}",
        f"static_init_start = 0x{static_init_start:08x}",
        f"static_init_end = 0x{static_init_end:08x}",
        "",
    ]
    content = "\n".join(lines)
    if extra_seeds_file and extra_seeds_file.is_file():
        content += "\n" + extra_seeds_file.read_text(encoding="utf-8") + "\n"
    path.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=pathlib.Path, required=True, help="Path to retail NSMB DS .nds ROM")
    parser.add_argument("--config-dir", type=pathlib.Path, default=pathlib.Path("config"), help="Path to config directory with symbols.txt/delinks.txt")
    parser.add_argument("--out", type=pathlib.Path, default=pathlib.Path("generated/inputs"), help="Target directory for prepared binaries and configs")
    args = parser.parse_args()

    rom_bytes = args.rom.read_bytes()
    rom_sha1 = sha1(rom_bytes)

    if rom_sha1 not in EXPECTED_ROMS:
        print(f"Warning: ROM SHA-1 {rom_sha1} not in verified list.", file=sys.stderr)
        info = {"title": "New Super Mario Bros. (Custom)", "code": b"A2DE", "region": "Custom"}
    else:
        info = EXPECTED_ROMS[rom_sha1]

    rom = ndspy.rom.NintendoDSRom(rom_bytes)

    arm9 = code_compression.decompress(bytes(rom.arm9))
    if len(arm9) < len(rom.arm9):
        arm9 = bytes(rom.arm9)
    arm7 = bytes(rom.arm7)

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "arm9.bin").write_bytes(arm9)
    (out / "arm7.bin").write_bytes(arm7)

    arm9_start = int(rom.arm9RamAddress)
    arm9_end = arm9_start + len(arm9)

    symbols_path = args.config_dir / "symbols.txt"
    delinks_path = args.config_dir / "delinks.txt"
    functions = parse_functions(symbols_path, arm9_start, arm9_end)
    data_ranges = parse_data_ranges(delinks_path, arm9_start, arm9_end)

    program_slug = f"nsmb_{info['region'].lower()}"
    seeds_dir = args.config_dir / "seeds"

    # Only the exact decomp functions belong to the initial ARM9 image.
    # Autoload moves the tail of this image over its original addresses;
    # recursive discovery there would compile the pre-copy instructions.
    write_config(
        out / "arm9.toml",
        name=f"{info['title']} ARM9 main",
        program_id=f"{program_slug}_arm9",
        load_address=arm9_start,
        entry_pc=int(rom.arm9EntryAddress),
        binary=arm9,
        functions=functions,
        data_ranges=data_ranges,
        authoritative=True,
    )

    runtime_start, runtime = extract_arm9_runtime(arm9, arm9_start)
    (out / "arm9_runtime.bin").write_bytes(runtime)
    # These observed targets were attributed to the original image shifted
    # by -0x87e0. They belong to the post-autoload main-RAM copy, not ITCM.
    runtime_seeds = seeds_dir / "arm9_arm9_01ff7820.toml"
    if runtime_seeds.is_file():
        addresses = re.findall(r"^addr\s*=\s*(0x[0-9a-fA-F]+)",
                               runtime_seeds.read_text(encoding="utf-8"), re.MULTILINE)
        if any(not runtime_start <= int(addr, 16) < runtime_start + len(runtime)
               for addr in addresses):
            raise ValueError("Runtime seeds must stay inside the installed autoload block")
    write_config(
        out / "arm9_runtime.toml",
        name=f"{info['title']} ARM9 post-autoload main RAM",
        program_id=f"{program_slug}_arm9_runtime",
        load_address=runtime_start,
        entry_pc=runtime_start,
        binary=runtime,
        functions=[],
        data_ranges=[],
        extra_seeds_file=runtime_seeds,
        authoritative=False,
    )

    write_config(
        out / "arm7.toml",
        name=f"{info['title']} ARM7",
        program_id=f"{program_slug}_arm7",
        load_address=int(rom.arm7RamAddress),
        entry_pc=int(rom.arm7EntryAddress),
        binary=arm7,
        functions=[
            {
                "addr": int(rom.arm7EntryAddress),
                "size": 0,
                "mode": "arm",
                "name": "arm7_entry",
            }
        ],
        data_ranges=[],
        authoritative=False,
    )

    # Runtime WRAM and ITCM banks
    arm7_wram_seeds = seeds_dir / "arm7_arm7_037f7e50.toml"
    write_config(
        out / "arm7_wram.toml",
        name=f"{info['title']} ARM7 WRAM",
        program_id=f"{program_slug}_arm7_wram",
        load_address=0x037F7E50,
        entry_pc=0x037F8000,
        binary=arm7,
        functions=[],
        data_ranges=[],
        extra_seeds_file=arm7_wram_seeds if arm7_wram_seeds.is_file() else None,
        authoritative=False,
    )

    arm9_itcm_seeds = seeds_dir / "arm9_arm9_01fb4c80.toml"
    write_config(
        out / "arm9_itcm.toml",
        name=f"{info['title']} ARM9 ITCM",
        program_id=f"{program_slug}_arm9_itcm",
        load_address=0x01FB4C80,
        entry_pc=0x01FF8000,
        binary=arm9,
        functions=[],
        data_ranges=[],
        extra_seeds_file=arm9_itcm_seeds if arm9_itcm_seeds.is_file() else None,
        authoritative=False,
    )

    overlays_dir = out / "overlays"
    overlays_dir.mkdir(parents=True, exist_ok=True)
    overlay_manifest: list[dict[str, object]] = []

    for overlay_id, overlay in sorted(rom.loadArm9Overlays().items()):
        data = bytes(overlay.data)
        filename = f"arm9_overlay_{overlay_id:03d}.bin"
        (overlays_dir / filename).write_bytes(data)
        if int(overlay.ramAddress) < DS_MAIN_RAM_LIMIT:
            # Check for overlay seed matches
            seed_pattern = f"arm9_arm9_overlay_{overlay_id:03d}_*.toml"
            ov_seeds = list(seeds_dir.glob(seed_pattern)) if seeds_dir.is_dir() else []
            ov_seed_file = ov_seeds[0] if ov_seeds else None

            write_overlay_config(
                overlays_dir / f"arm9_overlay_{overlay_id:03d}.toml",
                title=info["title"],
                program_id=f"{program_slug}_arm9",
                overlay_id=overlay_id,
                load_address=int(overlay.ramAddress),
                binary=data,
                bss_size=int(overlay.bssSize),
                static_init_start=int(overlay.staticInitStart),
                static_init_end=int(overlay.staticInitEnd),
                extra_seeds_file=ov_seed_file,
            )
        overlay_manifest.append(
            {
                "id": overlay_id,
                "file": filename,
                "file_id": int(overlay.fileID),
                "load_address": f"0x{int(overlay.ramAddress):08x}",
                "size": int(overlay.ramSize),
                "bss_size": int(overlay.bssSize),
                "static_init_start": f"0x{int(overlay.staticInitStart):08x}",
                "static_init_end": f"0x{int(overlay.staticInitEnd):08x}",
                "compressed_in_rom": bool(overlay.compressed),
                "compressed_size": int(overlay.compressedSize),
                "sha1": sha1(data),
            }
        )

    (out / "overlays.json").write_text(
        json.dumps(overlay_manifest, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    print(f"Verified ROM: {info['title']} [{info['code'].decode('ascii')}] SHA-1: {rom_sha1}")
    print(f"Extracted ARM9: {len(arm9):,} bytes ({len(functions)} functions, {len(data_ranges)} data ranges)")
    print(f"Extracted ARM7: {len(arm7):,} bytes")
    print(f"Extracted Overlays: {len(overlay_manifest)} overlays inventoried to {overlays_dir}")
    print(f"Generated input manifests in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
