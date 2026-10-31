#!/usr/bin/env python3
"""Render Medium posts as readable, linked, native SVG cards for a GitHub profile."""

from __future__ import annotations

import argparse
from datetime import timezone
from email.utils import parsedate_to_datetime
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
import re
import textwrap
from urllib.parse import urlparse
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

FEED_URL = "https://medium.com/feed/@selcuk.san"
START = "<!-- medium-posts:start -->"
END = "<!-- medium-posts:end -->"
MAX_POSTS = 5


class FirstParagraph(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_p = False
        self.parts = []
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        if tag in ("figure", "pre", "blockquote", "script", "style"):
            self.skip += 1
        elif tag == "p" and not self.skip:
            self.in_p = True
            self.parts = []

    def handle_endtag(self, tag):
        if tag == "p" and self.in_p:
            sentence = " ".join("".join(self.parts).split())
            if len(sentence) > 35:
                self.paragraphs.append(sentence)
            self.in_p = False
        elif tag in ("figure", "pre", "blockquote", "script", "style"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if self.in_p and not self.skip:
            self.parts.append(data)


def description(html: str, max_chars: int = 120) -> str:
    parser = FirstParagraph()
    parser.feed(html)
    text = " ".join(unescape(parser.paragraphs[0]).split()) if parser.paragraphs else ""
    if len(text) > max_chars:
        text = text[:max_chars].rsplit(" ", 1)[0].rstrip(".,;: ") + "…"
    return text


def read_posts(data: bytes) -> list[dict]:
    root = ET.fromstring(data)
    posts = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        parsed = urlparse(link)
        if not title or parsed.scheme != "https" or parsed.netloc.lower() not in ("medium.com", "www.medium.com"):
            continue
        content = (item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
                   or item.findtext("description") or "")
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "").astimezone(timezone.utc).strftime("%d %b %Y").upper()
        except (TypeError, ValueError, OverflowError):
            published = ""
        tags = [e.text.strip() for e in item.findall("category") if e.text and e.text.strip()]
        posts.append({
            "title": title, "url": link, "date": published,
            "topic": tags[0].upper() if tags else "TECHNICAL ARTICLE",
            "description": description(content),
        })
        if len(posts) >= MAX_POSTS:
            break
    if not posts:
        raise ValueError("No Medium articles in the feed; existing README remains unchanged")
    return posts


def wrap(text: str, width: int, max_lines: int) -> list[str]:
    lines = textwrap.wrap(text, width=width, break_long_words=False, break_on_hyphens=False)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .") + "…"
    return lines


def svg_card(post: dict, index: int, total: int) -> str:
    """Compact card: narrower text and shorter canvas, without losing hierarchy."""
    featured = index == 0
    height = 160 if featured else 124
    title_y = 68 if featured else 65
    title_size = 22 if featured else 20
    title_lines = wrap(post["title"], 53 if featured else 58, 2)
    summary = wrap(post["description"], 95, 1) if featured and post["description"] else []
    title_svg = "\n".join(
        f'  <text x="30" y="{title_y + i * 27}" fill="#f8fafc" font-size="{title_size}" font-weight="700">{escape(line)}</text>'
        for i, line in enumerate(title_lines)
    )
    subtitle_svg = (f'  <text x="30" y="119" fill="#aebdd1" font-size="12">{escape(summary[0])}</text>\n'
                    if summary else "")
    subject = post["topic"]
    if len(subject) > 35:
        subject = subject[:34].rsplit(" ", 1)[0] + "…"
    date_svg = (f'<text x="810" y="{height - 18}" font-size="10" font-weight="600" '
                f'fill="#8191aa" text-anchor="end">{escape(post["date"])}</text>'
                if post["date"] else "")
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 840 {height}" width="840" height="{height}" role="img" aria-label="{escape(post['title'], quote=True)}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#131f32"/><stop offset="1" stop-color="#0b1220"/></linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#75e5ca"/><stop offset="1" stop-color="#6088f0"/></linearGradient>
  </defs>
  <rect x="1" y="1" width="838" height="{height-2}" rx="14" fill="url(#bg)" stroke="#2c3a4f" stroke-width="2"/>
  <rect x="1" y="20" width="5" height="{height-40}" rx="2" fill="url(#accent)"/>
  <circle cx="742" cy="10" r="72" fill="none" stroke="#75e5ca" stroke-opacity="0.08" stroke-width="25"/>
  <circle cx="742" cy="10" r="113" fill="none" stroke="#93a8f5" stroke-opacity="0.05" stroke-width="22"/>
  <text x="30" y="26" fill="#74dec9" font-family="Arial, Helvetica, sans-serif" font-size="10" font-weight="700" letter-spacing="1.8">{('FEATURED STORY' if featured else 'ENGINEERING NOTES')}</text>
  <text x="810" y="26" text-anchor="end" fill="#7d8fa9" font-family="Arial, Helvetica, sans-serif" font-size="10" font-weight="700">{index+1:02d} / {total:02d}</text>
  <g font-family="Arial, Helvetica, sans-serif">
{title_svg}
{subtitle_svg}  <text x="30" y="{height - 18}" font-size="10" font-weight="600" letter-spacing="0.6" fill="#91b1ca">{escape(subject)}</text>
    {date_svg}
  </g>
  <path d="M794 {height // 2 - 6} l7 7 -7 7 M801 {height // 2 + 1} h-22" stroke="#75e5ca" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none"/>
</svg>
'''



def section(posts: list[dict]) -> str:
    lines = [START]
    for i, post in enumerate(posts):
        image = f"assets/medium/article-{i+1:02d}.svg"
        lines.extend([
            '<p align="center">',
            f'  <a href="{escape(post["url"], quote=True)}">',
            f'    <img src="{image}" alt="{escape(post["title"], quote=True)}" width="90%">',
            '  </a>',
            '</p>',
            ''
        ])
    lines.extend([
        '<p align="right"><a href="https://medium.com/@selcuk.san">Read all articles on Medium ↗</a></p>',
        END
    ])
    return "\n".join(lines)


def update(readme_path: Path, assets: Path, posts: list[dict]) -> None:
    current = readme_path.read_text(encoding="utf-8")
    if current.count(START) != 1 or current.count(END) != 1:
        raise ValueError("Expected exactly one pair of Medium markers; nothing changed")
    replacement = re.sub(re.escape(START) + r".*?" + re.escape(END),
                         lambda _: section(posts), current, flags=re.S, count=1)
    cards = [(assets / f"article-{i+1:02d}.svg", svg_card(post, i, len(posts)))
             for i, post in enumerate(posts)]
    assets.mkdir(parents=True, exist_ok=True)
    for path, content in cards:
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            path.write_text(content, encoding="utf-8")
    if replacement != current:
        readme_path.write_text(replacement, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    parser.add_argument("--assets", type=Path, default=Path("assets/medium"))
    parser.add_argument("--feed-file", type=Path)
    args = parser.parse_args()
    if args.feed_file:
        feed = args.feed_file.read_bytes()
    else:
        req = Request(FEED_URL, headers={"User-Agent": "github-profile-medium-cards/2.0"})
        with urlopen(req, timeout=25) as response:
            feed = response.read()
    update(args.readme, args.assets, read_posts(feed))


if __name__ == "__main__":
    main()
