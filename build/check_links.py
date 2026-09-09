#!/usr/bin/env python3
"""Проверка ссылок в гайде: локальные пути и якоря, плюс список внешних URL.

    python3 build/check_links.py            # только локальные, быстро
    python3 build/check_links.py --external # ещё и постучаться во внешние

Локальные ссылки проверяются всегда: битая ссылка внутри репозитория — это то, что
читатель встретит первым, и починить её ничего не стоит.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")


def anchors(path: Path) -> set[str]:
    """Якоря, которые GitHub делает из заголовков markdown."""
    found = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            continue
        title = line.lstrip("#").strip()
        slug = "".join(
            ch for ch in title.lower().replace(" ", "-")
            if ch.isalnum() or ch in "-_" or unicodedata.category(ch).startswith("L")
        )
        found.add(slug)
    return found


def main() -> int:
    check_external = "--external" in sys.argv
    broken: list[str] = []
    external: set[str] = set()

    for md in sorted(ROOT.rglob("*.md")):
        if ".git" in md.parts:
            continue
        for target in LINK.findall(md.read_text(encoding="utf-8")):
            if target.startswith(("http://", "https://")):
                external.add(target)
                continue
            if target.startswith("#"):
                path, anchor = md, target[1:]
            else:
                rel, _, anchor = target.partition("#")
                path = (md.parent / rel).resolve()
            if not path.exists():
                broken.append(f"{md.relative_to(ROOT)} → {target} (нет файла)")
                continue
            if anchor and path.suffix == ".md" and anchor not in anchors(path):
                broken.append(f"{md.relative_to(ROOT)} → {target} (нет якоря)")

    print(f"локальных ссылок проверено, битых: {len(broken)}")
    for item in broken:
        print(f"  БИТАЯ  {item}")

    print(f"внешних URL: {len(external)}")
    if check_external:
        for url in sorted(external):
            try:
                with urlopen(Request(url, method="HEAD",
                                     headers={"User-Agent": "link-check"}), timeout=20) as resp:
                    code = resp.status
            except HTTPError as exc:
                code = exc.code
            except (URLError, OSError) as exc:
                code = f"нет ответа ({type(exc).__name__})"
            mark = "ok " if code in (200, 301, 302, 403) else "!!!"
            print(f"  {mark} {code}  {url}")

    return 1 if broken else 0


if __name__ == "__main__":
    raise SystemExit(main())
