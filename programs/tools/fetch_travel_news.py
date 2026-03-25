#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[2]
OUTPUTS = ROOT / "outputs"
NEWS_DIR = OUTPUTS / "news"
RESEARCH_MD = OUTPUTS / "research" / "competitors" / "latest.md"
JNTO_MEDIA_RELEASES = "https://www.japan.travel/en/au/media-releases/"


def fetch_jnto_news(limit: int = 5) -> list[dict[str, str]]:
    html = requests.get(JNTO_MEDIA_RELEASES, timeout=30).text
    soup = BeautifulSoup(html, "html.parser")
    items: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    pattern = re.compile(r"^(?P<title>.+?)\s+(?P<date>\d{1,2}\s+\w+\s+\d{4})\s+JNTO", re.DOTALL)

    for link in soup.find_all("a", href=True):
        text = " ".join(link.get_text(" ", strip=True).split())
        match = pattern.match(text)
        if not match:
            continue
        url = urljoin(JNTO_MEDIA_RELEASES, link["href"])
        if url in seen_urls:
            continue
        seen_urls.add(url)
        items.append(
            {
                "source": "JNTO",
                "type": "official",
                "title": match.group("title").strip(),
                "date": match.group("date").strip(),
                "url": url,
            }
        )
        if len(items) >= limit:
            break
    return items


def fetch_research_watch(limit: int = 4) -> list[dict[str, str]]:
    if not RESEARCH_MD.exists():
        return []
    lines = RESEARCH_MD.read_text(encoding="utf-8").splitlines()
    items: list[dict[str, str]] = []
    current_channel = ""
    for line in lines:
        if line.startswith("### "):
            current_channel = line.replace("### ", "").strip()
            continue
        if not line.startswith("- 20"):
            continue
        parts = line[2:].split(" | ")
        if len(parts) < 3:
            continue
        items.append(
            {
                "source": current_channel or "Research",
                "type": "sns_watch",
                "date": parts[0].strip(),
                "title": parts[1].strip(),
                "url": parts[2].strip(),
            }
        )
        if len(items) >= limit:
            break
    return items


def main() -> None:
    NEWS_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "created_at_jst": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "headline_note": "JNTOの公式リリースと、直近の競合リサーチから見たSNSウォッチを混在表示しています。",
        "official_news": fetch_jnto_news(),
        "sns_watch": fetch_research_watch(),
    }
    latest_path = NEWS_DIR / "latest_travel_news.json"
    latest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"travel_news={latest_path}")


if __name__ == "__main__":
    main()
