#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
GENERIC_GENERATOR = TOOLS_DIR / "generate_openai_generic_short.py"


def load_packet(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_packet(path: Path, packet: dict) -> None:
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_artifacts(stdout: str) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for line in stdout.splitlines():
        match = re.match(r"^(saved|manifest|manifest_index)=(.+)$", line.strip())
        if match:
            artifacts[match.group(1)] = match.group(2).strip()
    return artifacts


def apply_generator_env(env: dict[str, str], packet: dict) -> None:
    prompt = packet.get("prompt", {})
    generator = packet.get("generator", {})

    prompt_text = str(prompt.get("editable_override") or prompt.get("text") or "").strip()
    if prompt_text:
        env["OPENAI_VIDEO_PROMPT_OVERRIDE"] = prompt_text

    field_map = {
        "idea_id": "OPENAI_VIDEO_IDEA_ID",
        "output_stem": "OPENAI_VIDEO_OUTPUT_STEM",
        "model": "OPENAI_VIDEO_MODEL",
        "size": "OPENAI_VIDEO_SIZE",
        "seconds": "OPENAI_VIDEO_SECONDS",
        "usd_per_sec": "OPENAI_VIDEO_USD_PER_SEC",
    }
    for key, env_name in field_map.items():
        value = generator.get(key)
        if value not in (None, ""):
            env[env_name] = str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", required=True, help="path to prompt_packet.json")
    args = parser.parse_args()

    packet_path = Path(args.packet).expanduser().resolve()
    if not packet_path.exists():
        raise SystemExit(f"Packet not found: {packet_path}")
    if not GENERIC_GENERATOR.exists():
        raise SystemExit(f"Generator script not found: {GENERIC_GENERATOR}")

    packet = load_packet(packet_path)
    if packet.get("approval_status") != "approved":
        raise SystemExit("Prompt packet is not approved. Refusing generation.")

    env = os.environ.copy()
    apply_generator_env(env, packet)

    proc = subprocess.run(
        [sys.executable, str(GENERIC_GENERATOR), "--generate"],
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    if proc.returncode != 0:
        raise SystemExit(proc.returncode)

    artifacts = parse_artifacts(proc.stdout)
    packet["generated_assets"] = {
        "video_path": artifacts.get("saved", ""),
        "manifest_path": artifacts.get("manifest", ""),
        "manifest_index_path": artifacts.get("manifest_index", ""),
    }
    save_packet(packet_path, packet)


if __name__ == "__main__":
    main()
