#!/usr/bin/env python3
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LATEST_PATH = ROOT / "latest-news.json"
SITEMAP_PATH = ROOT / "page-sitemap.xml"
BASE_URL = "https://insight-forge-site.pages.dev"
DISQUS_SRC = "https://mytechblog-4.disqus.com/embed.js"
ADS_CLIENT = "ca-pub-3756147512527882"
ADS_SLOT = "7208765893"
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
FORCE_CATEGORY = os.getenv("ARTICLE_CATEGORY", "auto").strip()

CATEGORY_PAGES = {
    "Anime": "anime.html",
    "Movies": "movies.html",
    "Technology": "tech.html",
    "Space": "space-science.html",
    "Gaming": "gaming.html",
}
CATEGORY_IMAGES = {
    "Anime": "image/latest-anime.svg",
    "Movies": "image/latest-movies.svg",
    "Technology": "image/latest-tech.svg",
    "Space": "image/latest-space.svg",
    "Gaming": "image/latest-gaming.svg",
}


def die(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def now_local() -> dt.datetime:
    return dt.datetime.now(ZoneInfo("Asia/Kolkata"))


def choose_category(today: dt.datetime) -> str | None:
    if FORCE_CATEGORY and FORCE_CATEGORY.lower() != "auto":
        if FORCE_CATEGORY not in CATEGORY_PAGES:
            die(f"Unknown ARTICLE_CATEGORY: {FORCE_CATEGORY}")
        return FORCE_CATEGORY
    rotation = ["Technology", "Movies", "Anime", "Space", "Gaming"]
    return rotation[today.weekday() % len(rotation)]


def call_gemini(prompt: str) -> dict:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        die("GEMINI_API_KEY GitHub secret is not configured.")

    schema = {
        "type": "object",
        "properties": {
            "publish": {"type": "boolean"},
            "reason": {"type": "string"},
            "title": {"type": "string"},
            "slug": {"type": "string"},
            "category": {"type": "string", "enum": list(CATEGORY_PAGES)},
            "description": {"type": "string"},
            "intro": {"type": "string"},
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string"},
                        "paragraphs": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["heading", "paragraphs"],
                },
            },
            "sources": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "url": {"type": "string"},
                    },
                    "required": ["name", "url"],
                },
            },
        },
        "required": ["publish", "reason"],
    }

    payload = {
        "model": MODEL,
        "input": prompt,
        "tools": [{"type": "google_search"}, {"type": "url_context"}],
        "response_format": {
            "type": "text",
            "mime_type": "application/json",
            "schema": schema,
        },
        "generation_config": {
            "max_output_tokens": 6000,
            "temperature": 0.35,
        },
        "store": False,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://generativelanguage.googleapis.com/v1beta/interactions",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
            "User-Agent": "Insight-Forge-AutoArticle/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        die(f"Gemini API returned HTTP {exc.code}: {details[:1000]}")
    except Exception as exc:
        die(f"Gemini API request failed: {exc}")

    text = data.get("output_text")
    if not text:
        chunks = []
        for step in data.get("steps", []) or []:
            for block in step.get("content", []) or []:
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    chunks.append(block["text"])
        text = "\n".join(chunks).strip()
    if not text:
        die("Gemini returned no text output.")

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        print(text[:3000], file=sys.stderr)
        die(f"Gemini returned invalid JSON: {exc}")


def normalize_slug(value: str, title: str, date_str: str) -> str:
    raw = (value or title).lower()
    raw = re.sub(r"&", " and ", raw)
    raw = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    raw = re.sub(r"-+", "-", raw)
    raw = raw[:78].strip("-")
    if not raw:
        raw = "insight-forge-news"
    return f"{raw}-{date_str}"


def validate_article(article: dict, existing_titles: set[str], existing_urls: set[str], today: str) -> dict:
    if not article.get("publish"):
        print(f"No article published: {article.get('reason', 'No suitable fresh topic found.')}")
        return article

    category = article.get("category")
    if category not in CATEGORY_PAGES:
        die(f"Invalid category from Gemini: {category}")

    title = str(article.get("title", "")).strip()
    description = str(article.get("description", "")).strip()
    intro = str(article.get("intro", "")).strip()
    if not title or not description or not intro:
        die("Generated article is missing title, description, or intro.")
    if len(title) > 110:
        die("Generated title is too long.")
    if title.casefold() in existing_titles:
        die("Generated topic duplicates an existing article title.")

    slug = normalize_slug(str(article.get("slug", "")), title, today)
    url_path = f"{slug}.html"
    if url_path in existing_urls or (ROOT / url_path).exists():
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%H%M%S")
        slug = slug + "-" + stamp
        url_path = f"{slug}.html"

    sections = article.get("sections") or []
    if not (3 <= len(sections) <= 7):
        die("Generated article must contain 3-7 sections.")
    for section in sections:
        if not section.get("heading") or not section.get("paragraphs"):
            die("Generated section is incomplete.")

    sources = article.get("sources") or []
    if len(sources) < 1:
        die("Generated article has no source links.")

    article["slug"] = slug
    article["url"] = url_path
    article["date"] = today
    article["category"] = category
    return article


def render_article(article: dict) -> str:
    title = html.escape(article["title"])
    desc = html.escape(article["description"])
    slug = article["slug"]
    canonical = f"{BASE_URL}/{slug}"
    date_str = article["date"]
    category = article["category"]
    image = CATEGORY_IMAGES[category]

    parts = [
        "<!DOCTYPE html>",
        '<html lang="en"><head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">',
        f"<title>{title} | Insight Forge</title>",
        f'<meta name="description" content="{desc}">',
        '<meta name="robots" content="index,follow,max-image-preview:large">',
        f'<link rel="canonical" href="{html.escape(canonical)}">',
        f'<meta property="og:title" content="{title}">',
        f'<meta property="og:description" content="{desc}">',
        '<meta property="og:type" content="article">',
        f'<meta property="og:url" content="{html.escape(canonical)}">',
        f'<meta property="og:image" content="{BASE_URL}/{image}">',
        f'<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={ADS_CLIENT}" crossorigin="anonymous"></script>',
        "<script type=\"application/ld+json\">" + json.dumps({
            "@context": "https://schema.org",
            "@type": "NewsArticle",
            "headline": article["title"],
            "description": article["description"],
            "datePublished": date_str,
            "dateModified": date_str,
            "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
            "image": [f"{BASE_URL}/{image}"],
            "author": {"@type": "Organization", "name": "Insight Forge"},
            "publisher": {"@type": "Organization", "name": "Insight Forge"},
        }, ensure_ascii=False) + "</script>",
        '<style>body{font-family:Arial,sans-serif;margin:0;background:#f5f7fa;color:#1f2937;line-height:1.8}.container{max-width:900px;margin:auto;padding:24px}header{background:#0f172a;color:#fff;padding:28px;text-align:center}nav{background:#1e293b;padding:12px;text-align:center}nav a{color:#fff;text-decoration:none;margin:0 10px}main{background:#fff;padding:28px;margin-top:24px;border-radius:12px}main img.hero{display:block;width:100%;max-height:340px;object-fit:cover;border-radius:14px;margin:12px 0 26px}h1,h2{color:#111827}.meta{color:#64748b;font-size:.95rem}.ad{margin:32px 0}footer{text-align:center;padding:24px;color:#64748b}a{color:#2563eb}</style>',
        "</head><body>",
        f'<header><h1>{title}</h1><p>{html.escape(category)} • {date_str}</p></header>',
        '<nav><a href="index.html">Home</a><a href="latest-news.html">Latest</a><a href="anime.html">Anime</a><a href="movies.html">Movies</a><a href="tech.html">Tech</a><a href="space-science.html">Space</a><a href="gaming.html">Gaming</a></nav>',
        "<main>",
        f'<img class="hero" src="{html.escape(image)}" alt="{html.escape(category)} news from Insight Forge" loading="eager">',
        f'<p class="meta"><strong>Published:</strong> {date_str}</p>',
        f'<p>{html.escape(article["intro"])}</p>',
    ]
    parts.append(f'<div class="ad"><ins class="adsbygoogle" style="display:block;text-align:center" data-ad-layout="in-article" data-ad-format="fluid" data-ad-client="{ADS_CLIENT}" data-ad-slot="{ADS_SLOT}"></ins><script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script></div>')

    for section in article["sections"]:
        parts.append(f'<h2>{html.escape(str(section["heading"]))}</h2>')
        for paragraph in section["paragraphs"]:
            parts.append(f'<p>{html.escape(str(paragraph))}</p>')

    parts.append('<div class="ad"><ins class="adsbygoogle" style="display:block;text-align:center" data-ad-format="autorelaxed" data-ad-client="%s"></ins><script>(adsbygoogle=window.adsbygoogle||[]).push({});</script></div>' % ADS_CLIENT)
    parts.append("<h2>Sources</h2><ul>")
    for source in article["sources"]:
        name = html.escape(str(source.get("name", "Source")))
        url = str(source.get("url", "")).strip()
        if not re.match(r"^https?://", url):
            continue
        parts.append(f'<li><a href="{html.escape(url, quote=True)}" target="_blank" rel="noopener nofollow">{name}</a></li>')
    parts.append("</ul>")
    parts.append('<div id="disqus_thread"></div>')
    parts.append(
        "<script>var disqus_config=function(){this.page.url=window.location.href;this.page.identifier="
        + json.dumps(slug)
        + ";};(function(){var d=document,s=d.createElement('script');s.src="
        + json.dumps(DISQUS_SRC)
        + ";s.setAttribute('data-timestamp',+new Date());(d.head||d.body).appendChild(s)})();</script>"
    )
    parts.extend(["</main>", "<footer>© 2026 Insight Forge</footer>", "</body></html>"])
    return "".join(parts)


def write_latest(article: dict, latest: list) -> None:
    item = {
        "title": article["title"],
        "category": article["category"],
        "date": article["date"],
        "url": article["url"],
        "image": CATEGORY_IMAGES[article["category"]],
        "alt": f"Insight Forge {article['category']}",
    }
    updated = [item] + [x for x in latest if x.get("url") != item["url"]]
    LATEST_PATH.write_text(json.dumps(updated[:80], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def update_sitemap(article: dict) -> None:
    sitemap = SITEMAP_PATH.read_text(encoding="utf-8")
    loc = f"{BASE_URL}/{article['slug']}"
    if f"<loc>{loc}</loc>" in sitemap:
        return
    block = f'  <url><loc>{loc}</loc><lastmod>{article["date"]}</lastmod><changefreq>weekly</changefreq><priority>0.7</priority></url>\n'
    if "</urlset>" not in sitemap:
        die("page-sitemap.xml has no closing </urlset> tag.")
    SITEMAP_PATH.write_text(sitemap.replace("</urlset>", block + "</urlset>"), encoding="utf-8")


def update_category_page(article: dict) -> None:
    path = ROOT / CATEGORY_PAGES[article["category"]]
    if not path.exists():
        print(f"WARN: category page missing: {path}")
        return
    text = path.read_text(encoding="utf-8")
    card = (
        '<article class="card"><span class="tag">'
        + html.escape(article["date"])
        + '</span><a href="'
        + html.escape(article["url"], quote=True)
        + '">'
        + html.escape(article["title"])
        + "</a></article>"
    )
    pattern = re.compile(
        r'(<section\b[^>]*>.*?<h2>[^<]*Latest[^<]*</h2>.*?<div class="article-grid">)(.*?)(</div></section>)',
        re.S | re.I,
    )
    match = pattern.search(text)
    if not match:
        print(f"WARN: no Latest section found in {path.name}")
        return
    body = match.group(2)
    cards = re.findall(r'<article class="card">.*?</article>', body, re.S)
    cards = [c for c in cards if article["url"] not in c]
    cards.insert(0, card)
    body_new = "\n".join(cards[:6])
    new_text = text[:match.start(2)] + "\n" + body_new + "\n" + text[match.end(2):]
    path.write_text(new_text, encoding="utf-8")


def main() -> None:
    today_dt = now_local()
    today = today_dt.date().isoformat()
    category = choose_category(today_dt)
    latest = read_json(LATEST_PATH, [])
    if not isinstance(latest, list):
        die("latest-news.json must contain a JSON array.")

    existing_titles = {str(x.get("title", "")).casefold() for x in latest}
    existing_urls = {str(x.get("url", "")) for x in latest}
    category_hint = category or "Any of Technology, Movies, Anime, Space, or Gaming"
    existing_sample = "\n".join(
        f"- {x.get('title','')} | {x.get('category','')} | {x.get('date','')}"
        for x in latest[:25]
    )

    prompt = f"""
You are the newsroom automation for Insight Forge, a small English-language technology/entertainment/science/gaming news site.
Today is {today} in India (Asia/Kolkata).
Your job is to find ONE genuinely fresh news topic and prepare a publish-ready original article.
Preferred category for today's run: {category_hint}.

Use Google Search to research current coverage from the last 72 hours. Prefer an official source for primary facts plus at least one reputable independent source when available. Use URL Context on important source pages when helpful. Do not rely on your memory for current facts.

Rules:
- Choose a topic that is materially new or has a meaningful update; do not invent a "news" angle from old information.
- Do not duplicate any recent Insight Forge story listed below.
- Every factual claim should be supportable by the sources you found. Never invent quotes, prices, specifications, release dates, cast members, statistics, or statements.
- If sources disagree, say so clearly instead of choosing an unsupported version.
- Paraphrase. Never copy article text, headlines, or long passages from sources.
- Write around 800-1200 words in clear, useful English, with context and what readers should watch next.
- The article must be useful on its own, not just a rewritten headline.
- Return source URLs exactly as https://... links that can be opened by a reader.
- Do not use HTML, Markdown, emojis, or citations inside the article text. Plain text only.
- The slug should be short, lowercase, hyphen-separated, and should not contain a date unless useful.

Recent Insight Forge stories:
{existing_sample}

Return JSON matching the provided schema. Set publish=false when there is no sufficiently fresh, well-sourced topic.
"""

    article = call_gemini(prompt)
    if not article.get("publish"):
        print(f"SKIP: {article.get('reason', 'No publishable story.')}")
        return

    article = validate_article(article, existing_titles, existing_urls, today)
    out_path = ROOT / article["url"]
    out_path.write_text(render_article(article), encoding="utf-8")
    write_latest(article, latest)
    update_sitemap(article)
    update_category_page(article)
    print(f"PUBLISHED: {article['title']}")
    print(f"URL: {BASE_URL}/{article['slug']}")
    print(f"CATEGORY: {article['category']}")


if __name__ == "__main__":
    main()
