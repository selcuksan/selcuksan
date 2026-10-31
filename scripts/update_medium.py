#!/usr/bin/env python3
"""Refresh the Medium section in the GitHub profile README using the RSS feed."""

from __future__ import annotations

import argparse
from email.utils import parsedate_to_datetime
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

FEED_URL = "https://medium.com/feed/@selcuk.san"
PROFILE_URL = "https://medium.com/@selcuk.san"
START = "<!-- medium-posts:start -->"
END = "<!-- medium-posts:end -->"
MAX_POSTS = 5


class ReadableText(HTMLParser):
    """Get the opening paragraph without figures or code examples."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.in_paragraph = False
        self.current = []
        self.paragraphs = []

    def handle_starttag(self, tag, attrs):
        if tag in ("figure", "pre", "script", "style", "blockquote"):
            self.skip += 1
        elif tag == "p" and not self.skip:
            self.in_paragraph = True
            self.current = []

    def handle_endtag(self, tag):
        if tag == "p" and self.in_paragraph:
            text = " ".join("".join(self.current).split())
            if len(text) >= 35:
                self.paragraphs.append(text)
            self.in_paragraph = False
        elif tag in ("figure", "pre", "script", "style", "blockquote"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if self.in_paragraph and not self.skip:
            self.current.append(data)


def short_description(html, limit=185):
    parser = ReadableText()
    parser.feed(html)
    text = parser.paragraphs[0] if parser.paragraphs else re.sub(r"<[^>]*>", " ", html)
    text = " ".join(unescape(text).split())
    if len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0].rstrip(".,;: ") + "…"
    return text


def read_posts(xml):
    root = ET.fromstring(xml)
    posts = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link.startswith(("https://medium.com/", "http://medium.com/")):
            continue
        content = (item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
                   or item.findtext("description") or "")
        try:
            published = parsedate_to_datetime(item.findtext("pubDate") or "").strftime("%d %b %Y")
        except (TypeError, ValueError, OverflowError):
            published = ""
        tags = [e.text.strip() for e in item.findall("category") if e.text and e.text.strip()]
        posts.append({
            "title": title, "link": link, "published": published,
            "tags": " · ".join(tags[:2]), "description": short_description(content)
        })
        if len(posts) >= MAX_POSTS:
            break
    if not posts:
        raise ValueError("No valid Medium posts found; existing README has not been changed")
    return posts


def make_section(posts):
    lines = [START, "<table>", "  <tbody>"]
    for post in posts:
        metadata = " · ".join(x for x in (post["published"], post["tags"]) if x)
        lines += [
            "    <tr>",
            '      <td width="100%">',
            f'        <a href="{escape(post["link"], quote=True)}"><strong>{escape(post["title"])} ↗</strong></a>',
        ]
        if metadata:
            lines.append(f"        <br><sub>{escape(metadata)}</sub>")
        if post["description"]:
            lines.append(f'        <p>{escape(post["description"])}</p>')
        lines += ["      </td>", "    </tr>"]
    lines += [
        "  </tbody>", "</table>", "",
        f"[View all articles on Medium ↗]({PROFILE_URL})", END
    ]
    return "\n".join(lines)


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("--readme", type=Path, default=Path("README.md"))
    cli.add_argument("--feed-file", type=Path, help="Local XML feed for testing")
    args = cli.parse_args()

    if args.feed_file:
        feed = args.feed_file.read_bytes()
    else:
        request = Request(FEED_URL, headers={"User-Agent": "github-profile-medium-updater/1.0"})
        with urlopen(request, timeout=25) as response:
            feed = response.read()

    replacement = make_section(read_posts(feed))
    readme = args.readme.read_text(encoding="utf-8")
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError("README must contain exactly one pair of Medium section markers")
    updated = re.sub(re.escape(START) + r".*?" + re.escape(END),
                     lambda _: replacement, readme, count=1, flags=re.DOTALL)
    if updated != readme:
        args.readme.write_text(updated, encoding="utf-8")
        print("Medium section updated")
    else:
        print("No changes to Medium section")


if __name__ == "__main__":
    main()
