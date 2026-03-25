#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[2]
YOUTUBE_TOOLS_DIR = Path(os.environ.get("MEETJAPAN_YOUTUBE_TOOLS_DIR", str(ROOT / "youtube_tools")))
YOUTUBE_ENV_FILE = Path(os.environ.get("MEETJAPAN_YOUTUBE_ENV_FILE", str(ROOT / ".env")))
UPLOAD_SCRIPT = Path(os.environ.get("MEETJAPAN_YOUTUBE_UPLOAD_SCRIPT", str(YOUTUBE_TOOLS_DIR / "upload-youtube.mjs")))


def now_jst() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def parse_jst_local_to_utc_iso(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M")
    dt = dt.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
    return dt.astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")


def load_packet(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_packet(path: Path, packet: dict) -> None:
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_ui_state(packet: dict) -> dict:
    packet.setdefault("ui_state", {})
    packet["ui_state"].setdefault("generation", {})
    packet["ui_state"].setdefault("video_review", {})
    packet["ui_state"]["video_review"].setdefault("youtube_upload", {})
    return packet


def parse_dotenv(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip()
    return env


def build_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(parse_dotenv(YOUTUBE_ENV_FILE))
    return env


def extract_upload_result(stdout: str) -> tuple[str, str, str]:
    video_url = ""
    video_id = ""
    scheduled_at = ""
    url_match = re.findall(r"https://www\.youtube\.com/shorts/([A-Za-z0-9_-]+)", stdout)
    if url_match:
        video_id = url_match[-1]
        video_url = f"https://www.youtube.com/shorts/{video_id}"
    result_match = re.search(r"📊 Result:\s*(\{.*\})", stdout, re.DOTALL)
    if result_match:
        try:
            data = json.loads(result_match.group(1))
            video_id = data.get("videoId") or video_id
            video_url = data.get("videoUrl") or video_url
            scheduled_at = data.get("scheduledAt") or ""
        except json.JSONDecodeError:
            pass
    return video_url, video_id, scheduled_at


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet", required=True)
    args = parser.parse_args()

    packet_path = Path(args.packet).expanduser().resolve()
    packet = ensure_ui_state(load_packet(packet_path))
    review = packet["ui_state"]["video_review"]
    upload = review.setdefault("youtube_upload", {})
    publish_packet_path = Path(review.get("publish_packet_path", ""))
    log_path = packet_path.with_name("youtube_upload.log")

    if not publish_packet_path.exists():
        upload.update(
            {
                "status": "failed",
                "finished_at_jst": now_jst(),
                "error": "投稿承認パケットが見つかりません。",
                "log_path": str(log_path),
                "launcher_pid": "",
            }
        )
        save_packet(packet_path, packet)
        return

    publish_packet = json.loads(publish_packet_path.read_text(encoding="utf-8"))
    video_path = publish_packet.get("video", {}).get("path") or packet.get("generated_assets", {}).get("video_path")
    if not video_path or not Path(video_path).exists():
        upload.update(
            {
                "status": "failed",
                "finished_at_jst": now_jst(),
                "error": "投稿対象の動画ファイルが見つかりません。",
                "log_path": str(log_path),
                "launcher_pid": "",
            }
        )
        save_packet(packet_path, packet)
        return

    drafts = publish_packet.get("platform_post_draft", {}).get("youtube_shorts", {})
    title = drafts.get("title") or packet.get("review_ja", {}).get("title") or "MeetJapan Short"
    description = drafts.get("description") or ""
    tags = drafts.get("keywords") or []
    env = build_env()
    youtube_schedule = review.setdefault("youtube_schedule", {})
    scheduled_for_jst = youtube_schedule.get("scheduled_for_jst", "")
    scheduled_at_iso = parse_jst_local_to_utc_iso(scheduled_for_jst)

    proc = subprocess.run(
        [
            "node",
            str(UPLOAD_SCRIPT),
            str(video_path),
            title,
            description,
            ",".join(tags),
            scheduled_at_iso,
        ],
        cwd=str(YOUTUBE_TOOLS_DIR),
        env=env,
        text=True,
        capture_output=True,
    )

    combined_log = (proc.stdout or "") + ("\n" if proc.stdout and proc.stderr else "") + (proc.stderr or "")
    log_path.write_text(combined_log, encoding="utf-8")

    upload["launcher_pid"] = ""
    upload["log_path"] = str(log_path)
    upload["finished_at_jst"] = now_jst()

    if proc.returncode == 0:
        video_url, video_id, scheduled_at = extract_upload_result(proc.stdout or "")
        upload.update(
            {
                "status": "completed",
                "youtube_url": video_url,
                "youtube_video_id": video_id,
                "scheduled_at": scheduled_at,
                "scheduled_for_jst": scheduled_for_jst,
                "error": "",
            }
        )
        review["posted"] = True
        review["posted_at_jst"] = now_jst()
    else:
        combined_lower = combined_log.lower()
        status = "failed"
        error = "YouTube 投稿に失敗しました。"
        if "invalid_grant" in combined_lower:
            status = "auth_required"
            error = "YouTube の再認証が必要です。Google認証をやり直してから再投稿してください。"
        upload.update(
            {
                "status": status,
                "youtube_url": "",
                "youtube_video_id": "",
                "scheduled_at": "",
                "scheduled_for_jst": scheduled_for_jst,
                "error": error,
            }
        )

    save_packet(packet_path, packet)


if __name__ == "__main__":
    main()
