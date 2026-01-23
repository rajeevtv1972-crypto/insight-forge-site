#!/usr/bin/env python3
"""
Add or update <link rel="canonical"> tags in all .html files under a directory.
Creates a .bak file for each modified file.
Configure BASE_URL to match your deployed site.
"""

import os
import re
from pathlib import Path
import shutil

# ===== CONFIGURE THIS =====
BASE_URL = "https://insight-forge-site.pages.dev"   # <-- change if needed
SITE_ROOT = "."  # run from your repo root where the HTML files are
# ==========================

head_open_re = re.compile(r"<head[^>]*>", re.IGNORECASE)
canonical_re = re.compile(r'<link[^>]+rel=["\']canonical["\'][^>]*>', re.IGNORECASE)
head_section_re = re.compile(r"(<head[^>]*>)(.*?)(</head>)", re.IGNORECASE | re.DOTALL)

def make_canonical_url(rel_path):
    # Convert local path to URL path
    p = rel_path.replace(os.sep, "/")
    if p.endswith("index.html"):
        url_path = "/" + p[:-len("index.html")]
        if not url_path.endswith("/"):
            url_path += "/"
    else:
        # keep the filename (e.g., post.html)
        url_path = "/" + p
    # Normalize double slashes
    url_path = re.sub(r"//+", "/", url_path)
    # Remove leading '/./' if any
    url_path = url_path.replace("/./", "/")
    return BASE_URL.rstrip("/") + url_path

def process_file(path: Path):
    text = path.read_text(encoding="utf-8")
    m = head_section_re.search(text)
    if not m:
        print(f"[SKIP] no <head> in {path}")
        return False
    head_open, head_content, head_close = m.group(1), m.group(2), m.group(3)
    rel = os.path.relpath(path, SITE_ROOT)
    canonical_url = make_canonical_url(rel)
    new_tag = f'<link rel="canonical" href="{canonical_url}" />'

    if canonical_re.search(head_content):
        # replace existing canonical
        new_head_content = canonical_re.sub(new_tag, head_content)
        print(f"[UPDATE] {path} -> {canonical_url}")
    else:
        # insert canonical after opening <head> tag (keep formatting)
        new_head_content = head_content + "\n    " + new_tag + "\n"
        print(f"[ADD]    {path} -> {canonical_url}")

    new_text = text[:m.start(2)] + new_head_content + text[m.end(2):]
    # backup
    bak_path = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(path, bak_path)
    path.write_text(new_text, encoding="utf-8")
    return True

def main():
    root = Path(SITE_ROOT)
    html_files = list(root.rglob("*.html"))
    print(f"Found {len(html_files)} .html files")
    changed = 0
    for p in html_files:
        if process_file(p):
            changed += 1
    print(f"Done. Modified {changed} files. Backups saved with .bak")

if __name__ == "__main__":
    main()
