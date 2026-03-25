from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write_video_manifest(
    *,
    video_path: Path,
    manifests_dir: Path,
    idea_id: str,
    model: str,
    size: str,
    seconds: int,
    prompt: str,
    source_script: str,
    final_video_id: str,
    attempt_video_ids: list[str],
) -> dict[str, Any]:
    manifests_dir.mkdir(parents=True, exist_ok=True)
    stem = video_path.stem

    prompt_sha256 = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    payload: dict[str, Any] = {
        "manifest_version": 1,
        "created_at_utc": _utc_now_iso(),
        "video": {
            "filename": video_path.name,
            "absolute_path": str(video_path),
            "size_bytes": video_path.stat().st_size if video_path.exists() else None,
        },
        "generation": {
            "idea_id": idea_id,
            "source_script": source_script,
            "model": model,
            "size": size,
            "seconds": seconds,
            "final_video_id": final_video_id,
            "attempt_video_ids": attempt_video_ids,
            "prompt_sha256": prompt_sha256,
            "prompt_text": prompt,
        },
        "performance": {
            "youtube": {
                "views": None,
                "watch_hours": None,
                "avg_view_duration_sec": None,
                "likes": None,
                "comments": None,
                "shares": None,
                "saved": None,
            },
            "instagram": {
                "views": None,
                "likes": None,
                "comments": None,
                "shares": None,
                "saved": None,
                "avg_watch_time_sec": None,
            },
            "tiktok": {
                "views": None,
                "likes": None,
                "comments": None,
                "shares": None,
                "saved": None,
                "avg_watch_time_sec": None,
            },
        },
        "analysis_notes": [],
    }

    per_video_manifest_path = video_path.with_suffix(".manifest.json")
    central_manifest_path = manifests_dir / f"{stem}.manifest.json"

    per_video_manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    central_manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return {
        "per_video_manifest_path": str(per_video_manifest_path),
        "central_manifest_path": str(central_manifest_path),
        "prompt_sha256": prompt_sha256,
    }
