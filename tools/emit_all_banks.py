import argparse
import subprocess
import sys
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
INPUTS_DIR = PROJECT_ROOT / "generated" / "inputs"
RECOMP_DIR = PROJECT_ROOT / "generated" / "recomp"
COALESCED_BANKS = frozenset({"nsmb_arm9_itcm", "nsmb_arm9_runtime"})

banks = [
    # Exact main ARM9 functions; RAM code must also match the live image.
    {
        "bank": "nsmb_arm9",
        "config": INPUTS_DIR / "arm9.toml",
        "bin": INPUTS_DIR / "arm9.bin",
        "shards": 16,
        "flags": ["--stable-address-shards", "--max-function-bytes", "16384",
                  "--validate-live-bytes"],
    },
    # Exact post-autoload main-RAM block. The original ARM9 bank remains
    # authoritative and both variants must pass live-byte validation.
    {
        "bank": "nsmb_arm9_runtime",
        "config": INPUTS_DIR / "arm9_runtime.toml",
        "bin": INPUTS_DIR / "arm9_runtime.bin",
        "shards": 4,
        "flags": ["--validate-live-bytes"],
    },
    # Main ARM7
    {
        "bank": "nsmb_arm7",
        "config": INPUTS_DIR / "arm7.toml",
        "bin": INPUTS_DIR / "arm7.bin",
        "shards": 2,
        "flags": ["--max-function-bytes", "512", "--validate-live-bytes"],
    },
    # ARM7 WRAM (Sound Engine & Nitro SDK drivers resident at 0x037F7E50)
    {
        "bank": "nsmb_arm7_wram",
        "config": INPUTS_DIR / "arm7_wram.toml",
        "bin": INPUTS_DIR / "arm7.bin",
        "shards": 2,
        "flags": ["--validate-live-bytes"],
    },
    # ARM9 ITCM (Resident at 0x01FF7820 / 0x01FB4C80)
    {
        "bank": "nsmb_arm9_itcm",
        "config": INPUTS_DIR / "arm9_itcm.toml",
        "bin": INPUTS_DIR / "arm9.bin",
        "shards": 4,
        "flags": ["--validate-live-bytes"],
    },
    # Overlay 000: Mario Physics / Main Player Mechanics
    {
        "bank": "nsmb_arm9_ov000",
        "config": INPUTS_DIR / "overlays" / "arm9_overlay_000.toml",
        "bin": INPUTS_DIR / "overlays" / "arm9_overlay_000.bin",
        "shards": 4,
        "flags": ["--validate-live-bytes"],
    },
    # Overlay 008: Stage Actors / Enemy Logic
    {
        "bank": "nsmb_arm9_ov008",
        "config": INPUTS_DIR / "overlays" / "arm9_overlay_008.toml",
        "bin": INPUTS_DIR / "overlays" / "arm9_overlay_008.bin",
        "shards": 2,
        "flags": ["--validate-live-bytes"],
    },
    # Overlay 009: world-map code identified by live byte matching.
    {
        "bank": "nsmb_arm9_ov009",
        "config": INPUTS_DIR / "overlays" / "arm9_overlay_009.toml",
        "bin": INPUTS_DIR / "overlays" / "arm9_overlay_009.bin",
        "shards": 2,
        "flags": ["--validate-live-bytes"],
    },
    # Overlay 010
    {
        "bank": "nsmb_arm9_ov010",
        "config": INPUTS_DIR / "overlays" / "arm9_overlay_010.toml",
        "bin": INPUTS_DIR / "overlays" / "arm9_overlay_010.bin",
        "shards": 4,
        "flags": ["--validate-live-bytes"],
    },
    # Overlay 011: Stage Logic
    {
        "bank": "nsmb_arm9_ov011",
        "config": INPUTS_DIR / "overlays" / "arm9_overlay_011.toml",
        "bin": INPUTS_DIR / "overlays" / "arm9_overlay_011.bin",
        "shards": 2,
        "flags": ["--validate-live-bytes"],
    },
    # Overlay 012: Level Mechanics
    {
        "bank": "nsmb_arm9_ov012",
        "config": INPUTS_DIR / "overlays" / "arm9_overlay_012.toml",
        "bin": INPUTS_DIR / "overlays" / "arm9_overlay_012.bin",
        "shards": 2,
        "flags": ["--validate-live-bytes"],
    },
    # Overlay 054: Boss Battles
    {
        "bank": "nsmb_arm9_ov054",
        "config": INPUTS_DIR / "overlays" / "arm9_overlay_054.toml",
        "bin": INPUTS_DIR / "overlays" / "arm9_overlay_054.bin",
        "shards": 2,
        "flags": ["--validate-live-bytes"],
    },
]

def emission_order(specs):
    # runner/CMakeLists.txt sorts *_dispatch.c before registering title banks.
    # Sort the full filename: sorting bare bank names gives a different order
    # when one name is a prefix of another (arm9 / arm9_itcm).
    return sorted(specs, key=lambda b: b["bank"] + "_dispatch.c")


def preceding_dispatches(bank, specs, output_dir, framework_dir):
    if not framework_dir.is_dir():
        raise FileNotFoundError(f"Missing framework dispatch directory: {framework_dir}")
    # Both BIOS variants may be selected at runtime. Include firmware banks
    # conservatively too, even when a particular runner disables firmware.
    for cpu in ("arm9", "arm7"):
        for prefix in ("", "freebios_"):
            name = f"{cpu}_bios_dispatch.c" if not prefix else f"{prefix}{cpu}_dispatch.c"
            if not (framework_dir / name).is_file():
                raise FileNotFoundError(f"Missing preceding dispatch: {framework_dir / name}")
    paths = set(framework_dir.glob("*_dispatch.c"))
    current_name = bank + "_dispatch.c"
    # Include existing extra title banks as well as expected outputs. Missing
    # expected predecessors must stop emission rather than silently bypass
    # their priority. Including the other CPU is conservative and harmless.
    paths.update(p for p in output_dir.glob("*_dispatch.c") if p.name < current_name)
    paths.update(output_dir / (b["bank"] + "_dispatch.c") for b in specs
                 if b["bank"] + "_dispatch.c" < current_name)
    ordered = sorted(paths)
    for path in ordered:
        if not path.is_file():
            raise FileNotFoundError(f"Missing preceding dispatch: {path}")
    return ordered


def bank_command(recompiler, bank, specs, output_dir, framework_dir, coalesce=True):
    cmd = [
        str(recompiler),
        "--config", str(bank["config"]),
        "--bin", str(bank["bin"]),
        "--out", str(output_dir),
        "--bank", bank["bank"],
        "--shards", str(bank["shards"]),
    ] + bank["flags"]
    if coalesce and bank["bank"] in COALESCED_BANKS:
        if "--validate-live-bytes" not in bank["flags"]:
            raise ValueError("Fallthrough coalescing requires live-byte validation")
        cmd.append("--coalesce-fallthroughs")
        for path in preceding_dispatches(bank["bank"], specs, output_dir, framework_dir):
            cmd.extend(["--preceding-dispatch", str(path)])
    return cmd


def main(argv=None):
    parser = argparse.ArgumentParser(description="Emit the NSMB static code banks")
    parser.add_argument("--recompiler", type=pathlib.Path, required=True)
    parser.add_argument("--preceding-dispatch-dir", type=pathlib.Path,
                        default=PROJECT_ROOT / "ndsrecomp" / "generated",
                        help="Framework BIOS/firmware dispatch directory used by the runner")
    parser.add_argument("--coalesce-fallthroughs", action=argparse.BooleanOptionalAction,
                        default=True, help="Coalesce validated ARM9 ITCM/runtime fallthroughs")
    args = parser.parse_args(argv)
    recompiler = args.recompiler.resolve(strict=True)
    RECOMP_DIR.mkdir(parents=True, exist_ok=True)
    try:
        for bank in emission_order(banks):
            cmd = bank_command(recompiler, bank, banks, RECOMP_DIR,
                               args.preceding_dispatch_dir, args.coalesce_fallthroughs)
            print(f"=== Recompiling bank {bank['bank']} ===")
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                print(f"Error compiling {bank['bank']}:\n{res.stderr}\n{res.stdout}", file=sys.stderr)
                return res.returncode
            for line in res.stdout.splitlines():
                if "[emit]" in line or "[finder]" in line:
                    print(" ", line)
    except (OSError, ValueError) as exc:
        print(f"Cannot emit static banks: {exc}", file=sys.stderr)
        return 1
    print("All static banks successfully recompiled to", RECOMP_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
