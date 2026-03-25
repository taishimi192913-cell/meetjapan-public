#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "programs" / "tools"
ENV_CANDIDATES = [
    ROOT / ".env",
]


def now_jst() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def load_packet(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_packet(path: Path, packet: dict) -> None:
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_ui_state(packet: dict) -> dict:
    packet.setdefault("ui_state", {})
    packet["ui_state"].setdefault("generation", {})
    packet["ui_state"].setdefault("video_review", {})
    return packet


def load_openai_key_from_env_files() -> None:
    if os.environ.get("OPENAI_API_KEY"):
        return
    for env_path in ENV_CANDIDATES:
        if not env_path.exists():
            continue
        for raw_line in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() != "OPENAI_API_KEY":
                continue
            value = value.strip().strip('"').strip("'")
            if value:
                os.environ["OPENAI_API_KEY"] = value
                return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", required=True, help="path to prompt_packet.json")
    args = parser.parse_args()

    packet_path = Path(args.packet).expanduser().resolve()
    packet = ensure_ui_state(load_packet(packet_path))
    log_path = packet_path.with_name("generation_job.log")
    load_openai_key_from_env_files()
    child_proc: subprocess.Popen[str] | None = None
    terminate_requested = {"value": False}

    def handle_stop(signum, _frame) -> None:
        terminate_requested["value"] = True
        try:
            packet_now = ensure_ui_state(load_packet(packet_path))
            packet_now["ui_state"]["generation"]["status"] = "stopping"
            packet_now["ui_state"]["generation"]["error"] = "停止リクエストを受け付けました。"
            save_packet(packet_path, packet_now)
        except Exception:
            pass
        if child_proc and child_proc.poll() is None:
            try:
                os.killpg(child_proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

    signal.signal(signal.SIGTERM, handle_stop)
    signal.signal(signal.SIGINT, handle_stop)

    packet["ui_state"]["generation"] = {
        "status": "running",
        "started_at_jst": now_jst(),
        "finished_at_jst": "",
        "log_path": str(log_path),
        "output_video_path": "",
        "manifest_path": "",
        "error": "",
        "launcher_pid": os.getpid(),
        "child_pid": "",
    }
    save_packet(packet_path, packet)

    with log_path.open("w", encoding="utf-8") as log_file:
        child_proc = subprocess.Popen(
            ["python3", str(TOOLS / "generate_from_approved_prompt.py"), "--packet", str(packet_path)],
            text=True,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        packet = ensure_ui_state(load_packet(packet_path))
        packet["ui_state"]["generation"]["child_pid"] = child_proc.pid
        save_packet(packet_path, packet)
        while True:
            returncode = child_proc.poll()
            if returncode is not None:
                break
            time.sleep(1)

    packet = ensure_ui_state(load_packet(packet_path))
    packet["ui_state"]["generation"]["finished_at_jst"] = now_jst()
    packet["ui_state"]["generation"]["returncode"] = returncode
    packet["ui_state"]["generation"]["launcher_pid"] = ""
    packet["ui_state"]["generation"]["child_pid"] = ""

    generated_assets = packet.get("generated_assets", {})
    if terminate_requested["value"]:
        packet["ui_state"]["generation"]["status"] = "stopped"
        packet["ui_state"]["generation"]["error"] = "ユーザーが生成を停止しました。"
    elif returncode == 0:
        packet["ui_state"]["generation"]["status"] = "completed"
        packet["ui_state"]["generation"]["output_video_path"] = generated_assets.get("video_path", "")
        packet["ui_state"]["generation"]["manifest_path"] = generated_assets.get("manifest_path", "")
    else:
        log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
        packet["ui_state"]["generation"]["status"] = "failed"
        packet["ui_state"]["generation"]["error"] = log_text.strip().splitlines()[-1] if log_text.strip() else "Generation failed"

    save_packet(packet_path, packet)


if __name__ == "__main__":
    main()
