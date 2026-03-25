#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "programs" / "research" / "competitor_sources.sample.json"
OUTPUT_ROOT = ROOT / "outputs" / "research" / "competitors"


STOPWORDS = {
    "the", "and", "for", "from", "with", "this", "that", "your", "japan", "tokyo",
    "are", "into", "how", "what", "why", "you", "our", "out", "guide", "travel",
    "trip", "shorts", "short", "video", "best", "top"
}


def fetch_text(url: str) -> str:
    proc = subprocess.run(
        ["curl", "-L", "-A", "Mozilla/5.0", "-s", url],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def parse_feed(xml_text: str) -> list[dict]:
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
    }
    root = ET.fromstring(xml_text)
    rows: list[dict] = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        published = (entry.findtext("atom:published", default="", namespaces=ns) or "").strip()
        video_id = (entry.findtext("yt:videoId", default="", namespaces=ns) or "").strip()
        link_el = entry.find("atom:link", ns)
        link = link_el.attrib.get("href", "") if link_el is not None else ""
        rows.append(
            {
                "title": title,
                "published": published,
                "video_id": video_id,
                "url": link,
            }
        )
    return rows


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z0-9']+", text.lower())
    return [w for w in words if len(w) >= 3 and w not in STOPWORDS]


def build_summary(rows: list[dict]) -> dict:
    all_titles = [r["title"] for r in rows if r.get("title")]
    token_counter: Counter[str] = Counter()
    pattern_counter: Counter[str] = Counter()
    for title in all_titles:
        token_counter.update(tokenize(title))
        lowered = title.lower()
        if "?" in title:
            pattern_counter["question_title"] += 1
        if any(char.isdigit() for char in title):
            pattern_counter["number_in_title"] += 1
        if any(word in lowered for word in ["why", "how", "what", "inside", "secret", "never", "most", "best"]):
            pattern_counter["curiosity_hook"] += 1
        if any(word in lowered for word in ["day", "life", "routine", "trip", "walk", "tour"]):
            pattern_counter["lifestyle_journey"] += 1

    top_words = [{"word": word, "count": count} for word, count in token_counter.most_common(15)]
    return {
        "video_count": len(rows),
        "top_title_words": top_words,
        "pattern_counts": dict(pattern_counter),
    }


def write_markdown(
    path: Path,
    channels: list[dict],
    summary: dict,
    manual_watchlist: list[dict],
    errors: list[dict],
    *,
    per_channel_limit: int,
    top_word_limit: int,
) -> None:
    lines = [
        "# Competitor Research Snapshot",
        "",
        f"- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} JST",
        f"- Total recent videos: {summary['video_count']}",
        "",
        "## Frequent title words",
        "",
    ]
    for item in summary["top_title_words"][:top_word_limit]:
        lines.append(f"- `{item['word']}`: {item['count']}")

    if summary.get("pattern_counts"):
        lines.extend(["", "## Title pattern counts", ""])
        for key, value in sorted(summary["pattern_counts"].items()):
            lines.append(f"- `{key}`: {value}")

    lines.extend(["", "## Channel snapshots", ""])
    for channel in channels:
        lines.append(f"### {channel['name']}")
        lines.append(f"- Source: {channel['handle_url']}")
        lines.append(f"- Topic: {channel['topic']}")
        if channel.get("error"):
            lines.append(f"- Feed status: {channel['error']}")
            lines.append("")
            continue
        for row in channel["videos"][:per_channel_limit]:
            lines.append(f"- {row['published'][:10]} | {row['title']} | {row['url']}")
        lines.append("")

    lines.extend(["## Manual watchlist", ""])
    for item in manual_watchlist:
        lines.append(f"- {item['platform']}: {item['label']} | {item['url']}")

    if errors:
        lines.extend(["", "## Fetch errors", ""])
        for error in errors:
            lines.append(f"- {error['channel_name']}: {error['error']} | {error['feed_url']}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--detail-multiplier", type=int, default=1, help="Increase report density without changing sources")
    args = parser.parse_args()

    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    channels = config.get("youtube_channels", [])
    manual_watchlist = config.get("manual_watchlist", [])

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_ROOT / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    combined_rows: list[dict] = []
    channel_results: list[dict] = []
    fetch_errors: list[dict] = []

    for channel in channels:
        feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['channel_id']}"
        xml_text = fetch_text(feed_url)
        if not xml_text.lstrip().startswith("<?xml"):
            fetch_errors.append(
                {
                    "channel_name": channel["name"],
                    "feed_url": feed_url,
                    "error": "Non-XML response returned",
                }
            )
            channel_results.append({**channel, "feed_url": feed_url, "videos": [], "error": "Non-XML response"})
            continue
        rows = parse_feed(xml_text)
        for row in rows:
            row["channel_name"] = channel["name"]
            row["channel_id"] = channel["channel_id"]
            row["feed_url"] = feed_url
        combined_rows.extend(rows)
        channel_results.append({**channel, "feed_url": feed_url, "videos": rows})

    summary = build_summary(combined_rows)

    json_path = out_dir / "competitor_snapshot.json"
    csv_path = out_dir / "youtube_recent_videos.csv"
    md_path = out_dir / "research_report.md"
    latest_json = OUTPUT_ROOT / "latest.json"
    latest_md = OUTPUT_ROOT / "latest.md"

    payload = {
        "generated_at_jst": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "channels": channel_results,
        "summary": summary,
        "manual_watchlist": manual_watchlist,
        "errors": fetch_errors,
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["channel_name", "published", "title", "url", "video_id", "channel_id", "feed_url"],
        )
        writer.writeheader()
        writer.writerows(combined_rows)

    per_channel_limit = 5 * max(1, args.detail_multiplier)
    top_word_limit = 15 * max(1, args.detail_multiplier)
    write_markdown(
        md_path,
        channel_results,
        summary,
        manual_watchlist,
        fetch_errors,
        per_channel_limit=per_channel_limit,
        top_word_limit=top_word_limit,
    )
    write_markdown(
        latest_md,
        channel_results,
        summary,
        manual_watchlist,
        fetch_errors,
        per_channel_limit=per_channel_limit,
        top_word_limit=top_word_limit,
    )

    print(f"research_json={json_path}")
    print(f"research_csv={csv_path}")
    print(f"research_md={md_path}")
    print(f"latest_md={latest_md}")


if __name__ == "__main__":
    main()
