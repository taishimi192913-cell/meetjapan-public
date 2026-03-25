#!/usr/bin/env python3
import argparse
import os
import sys
import time
from pathlib import Path

import requests

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from manifest_utils import write_video_manifest

API_URL = "https://api.openai.com/v1/videos"
DEFAULT_SECONDS = 8
DEFAULT_MODEL = "sora-2"
DEFAULT_SIZE = "720x1280"
DEFAULT_USD_PER_SEC = 0.10

PROMPT = """
Create an 8-second vertical video (720x1280) for MeetJapan.
Language: English narration and English subtitles only.
Keep it realistic, tasteful, and retention-first.
"""


def get_active_prompt() -> str:
    return os.getenv("OPENAI_VIDEO_PROMPT_OVERRIDE", PROMPT).strip()


def get_model() -> str:
    return os.getenv("OPENAI_VIDEO_MODEL", DEFAULT_MODEL)


def get_size() -> str:
    return os.getenv("OPENAI_VIDEO_SIZE", DEFAULT_SIZE)


def get_seconds() -> int:
    return int(os.getenv("OPENAI_VIDEO_SECONDS", str(DEFAULT_SECONDS)))


def get_usd_per_sec() -> float:
    return float(os.getenv("OPENAI_VIDEO_USD_PER_SEC", str(DEFAULT_USD_PER_SEC)))


def get_idea_id() -> str:
    return os.getenv("OPENAI_VIDEO_IDEA_ID", "generic_meetjapan_short")


def get_output_stem() -> str:
    stem = os.getenv("OPENAI_VIDEO_OUTPUT_STEM", "")
    if stem:
        return stem
    return f"{get_idea_id()}_en"


def create_video(api_key: str):
    headers = {"Authorization": f"Bearer {api_key}"}
    files = {
        "model": (None, get_model()),
        "prompt": (None, get_active_prompt()),
        "seconds": (None, str(get_seconds())),
        "size": (None, get_size()),
    }
    r = requests.post(API_URL, headers=headers, files=files, timeout=180)
    if r.status_code >= 400:
        raise RuntimeError(f"create_video failed: status={r.status_code} body={r.text}")
    r.raise_for_status()
    return r.json()


def poll_video(api_key: str, video_id: str, timeout_sec: int = 1800):
    headers = {"Authorization": f"Bearer {api_key}"}
    status_url = f"{API_URL}/{video_id}"
    start = time.time()

    while time.time() - start < timeout_sec:
        r = requests.get(status_url, headers=headers, timeout=90)
        r.raise_for_status()
        j = r.json()
        status = (j.get("status") or "").lower()
        progress = j.get("progress")
        print(f"status={status} progress={progress}")

        if status == "completed":
            return j
        if status == "failed":
            raise RuntimeError(f"Video generation failed: {j}")
        time.sleep(10)

    raise TimeoutError("Video generation timed out")


def download_video(api_key: str, video_id: str, out_path: Path):
    headers = {"Authorization": f"Bearer {api_key}"}
    content_url = f"{API_URL}/{video_id}/content"
    with requests.get(content_url, headers=headers, stream=True, timeout=240) as resp:
        resp.raise_for_status()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)


def ensure_symlink(link_path: Path, target_rel: Path):
    if link_path.is_symlink():
        link_path.unlink()
    elif link_path.exists():
        backup = link_path.with_suffix(link_path.suffix + ".bak")
        idx = 1
        while backup.exists():
            backup = link_path.with_suffix(link_path.suffix + f".bak{idx}")
            idx += 1
        link_path.rename(backup)
        print(f"backup={backup}")
    link_path.symlink_to(target_rel)


def review_prompt():
    active_prompt = get_active_prompt()
    checks = {
        "english_only": ("Language: English" in active_prompt),
        "hook_early": ("Hook (0:00-0:01)" in active_prompt),
        "subtitle_spec": ("Subtitle style" in active_prompt),
        "visual_hook": ("visual curiosity first" in active_prompt.lower() or "visual curiosity" in active_prompt.lower()),
        "silent_viewing": ("watching without sound" in active_prompt),
    }
    est_cost = get_seconds() * get_usd_per_sec()
    print("=== Prompt Review ===")
    print(f"model={get_model()} size={get_size()} seconds={get_seconds()}")
    print(f"estimated_cost_usd={est_cost:.2f} (excl. retries)")
    for k, v in checks.items():
        print(f"{k}: {'OK' if v else 'MISSING'}")
    print("=====================")
    return all(checks.values())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--generate", action="store_true", help="Actually call the video API")
    args = parser.parse_args()

    prompt_ok = review_prompt()
    if not prompt_ok:
        raise SystemExit("Prompt review failed; fix prompt before generation.")
    if not args.generate:
        print("Draft-only mode complete. Re-run with --generate to create video.")
        return

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise SystemExit("OPENAI_API_KEY is not set")

    root_dir = Path(__file__).resolve().parents[2]
    base_dir = root_dir / "outputs"
    master_dir = base_dir / "master"
    ig_dir = base_dir / "instagram"
    tt_dir = base_dir / "tiktok"
    yt_dir = base_dir / "youtube"
    for d in (master_dir, ig_dir, tt_dir, yt_dir):
        d.mkdir(parents=True, exist_ok=True)

    final_video_id = None
    attempt_video_ids: list[str] = []
    for attempt in range(1, 4):
        print(f"Creating video job... attempt={attempt}")
        job = create_video(api_key)
        video_id = job.get("id")
        if not video_id:
            raise RuntimeError(f"No video id in response: {job}")
        print(f"video_id={video_id}")
        attempt_video_ids.append(video_id)

        try:
            poll_video(api_key, video_id, timeout_sec=900)
            final_video_id = video_id
            break
        except Exception as e:
            print(f"attempt={attempt} failed: {e}")
            if attempt == 3:
                raise

    stamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"{get_output_stem()}_{stamp}.mp4"
    master_output = master_dir / filename
    download_video(api_key, final_video_id, master_output)
    print(f"saved={master_output}")

    rel_target = Path("..") / "master" / filename
    ig_output = ig_dir / filename
    tt_output = tt_dir / filename
    yt_output = yt_dir / filename
    ensure_symlink(ig_output, rel_target)
    ensure_symlink(tt_output, rel_target)
    ensure_symlink(yt_output, rel_target)
    print(f"linked={ig_output} -> {rel_target}")
    print(f"linked={tt_output} -> {rel_target}")
    print(f"linked={yt_output} -> {rel_target}")

    manifest_info = write_video_manifest(
        video_path=master_output,
        manifests_dir=base_dir / "manifests",
        idea_id=get_idea_id(),
        model=get_model(),
        size=get_size(),
        seconds=get_seconds(),
        prompt=get_active_prompt(),
        source_script=str(Path(__file__).resolve()),
        final_video_id=final_video_id,
        attempt_video_ids=attempt_video_ids,
    )
    print(f"manifest={manifest_info['per_video_manifest_path']}")
    print(f"manifest_index={manifest_info['central_manifest_path']}")
    print(f"prompt_sha256={manifest_info['prompt_sha256']}")


if __name__ == "__main__":
    main()
