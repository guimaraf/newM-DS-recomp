import argparse
import subprocess
import sys
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description="Emit the NSMB static code banks")
parser.add_argument("--recompiler", type=pathlib.Path, required=True)
args = parser.parse_args()
RECOMPILER = str(args.recompiler.resolve(strict=True))
INPUTS_DIR = PROJECT_ROOT / "generated" / "inputs"
RECOMP_DIR = PROJECT_ROOT / "generated" / "recomp"

RECOMP_DIR.mkdir(parents=True, exist_ok=True)

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
    # Overlay 010: World Map & Main Gameplay Loop
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

for b in banks:
    cmd = [
        RECOMPILER,
        "--config", str(b["config"]),
        "--bin", str(b["bin"]),
        "--out", str(RECOMP_DIR),
        "--bank", b["bank"],
        "--shards", str(b["shards"]),
    ] + b["flags"]
    print(f"=== Recompiling bank {b['bank']} ===")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error compiling {b['bank']}:\n{res.stderr}\n{res.stdout}", file=sys.stderr)
        sys.exit(res.returncode)
    # Print the emit line
    for line in res.stdout.splitlines():
        if "[emit]" in line or "[finder]" in line:
            print(" ", line)

print("All static banks successfully recompiled to", RECOMP_DIR)
