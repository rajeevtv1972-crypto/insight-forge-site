#!/usr/bin/env python3
import datetime as dt
import difflib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://insight-forge-site.pages.dev/"

CATEGORY_KEYWORDS = {
    "Technology": ["technology", "AI", "hardware", "software", "smartphones"],
    "Anime": ["anime", "manga", "Japan", "season", "trailer"],
    "Movies": ["movies", "cinema", "film", "Hollywood", "streaming"],
    "Gaming": ["gaming", "video games", "PlayStation", "Xbox", "Nintendo"],
    "Space": ["space", "NASA", "SpaceX", "astronomy", "science"],
}

STOPWORDS = {
    "the","and","for","with","from","this","that","what","when","where","how",
    "why","new","news","latest","2026","2027","explained","update","guide",
    "review","details","official","first","reveals","revealed","arrives",
    "launches","insight","forge"
}

def read(path):
    return (ROOT / path).read_text(encoding="utf-8")

def write(path, content):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

def normalize(value):
    return re.sub(r"[^a-z0-9 ]+", " ", str(value or "").lower()).strip()

def title_similarity(a, b):
    na, nb = normalize(a), normalize(b)
    ta = {x for x in na.split() if len(x) > 2 and x not in STOPWORDS}
    tb = {x for x in nb.split() if len(x) > 2 and x not in STOPWORDS}
    if not ta or not tb:
        return difflib.SequenceMatcher(None, na, nb).ratio()
    return max(
        len(ta & tb) / max(1, len(ta | tb)),
        difflib.SequenceMatcher(None, na, nb).ratio() * 0.8,
        len(ta & tb) / max(1, min(len(ta), len(tb))) * 0.75,
    )

def domain(url):
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host

def extract_keywords(article):
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.-]{2,}", article["title"])
    seen = set()
    keywords = []
    for word in CATEGORY_KEYWORDS.get(article["category"], []) + words:
        key = word.lower()
        if key not in seen:
            seen.add(key)
            keywords.append(word)
    return keywords[:12]

def create_thumbnail(article):
    palette = {
        "Technology": ("#2563eb", "#7c3aed"),
        "Anime": ("#db2777", "#7c3aed"),
        "Movies": ("#dc2626", "#f59e0b"),
        "Gaming": ("#16a34a", "#0891b2"),
        "Space": ("#4f46e5", "#0891b2"),
    }
    a, b = palette[article["category"]]
    words = re.sub(r"\s+", " ", article["title"]).strip().split()
    lines, current = [], ""
    for word in words:
        candidate = (current + " " + word).strip()
        if current and len(candidate) > 30:
            lines.append(current)
            current = word
        else:
            current = candidate
        if len(lines) == 2:
            break
    if current and len(lines) < 3:
        lines.append(current)
    if len(" ".join(lines).split()) < len(words) and lines:
        lines[-1] = lines[-1].rstrip(" .") + "…"

    start_y = 288 - (len(lines) - 1) * 40
    spans = "".join(
        '<tspan x="72" y="{y}">{text}</tspan>'.format(
            y=start_y + i * 80,
            text=html.escape(line),
        )
        for i, line in enumerate(lines[:3])
    )

    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="675" viewBox="0 0 1200 675" role="img">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="{a}"/><stop offset="100%" stop-color="{b}"/></linearGradient></defs>
<rect width="1200" height="675" fill="url(#g)"/>
<circle cx="1010" cy="110" r="165" fill="#fff" opacity=".12"/><circle cx="1075" cy="545" r="225" fill="#fff" opacity=".08"/>
<path d="M0 555 C260 425 390 640 650 530 S1030 350 1220 455" fill="none" stroke="#fff" stroke-opacity=".16" stroke-width="3"/>
<text x="72" y="82" fill="#fff" fill-opacity=".78" font-family="Arial,Helvetica,sans-serif" font-size="28" font-weight="700" letter-spacing="3">{category}</text>
<rect x="72" y="115" width="108" height="6" rx="3" fill="#fff" fill-opacity=".62"/>
<text x="72" y="288" fill="#fff" font-family="Arial,Helvetica,sans-serif" font-size="58" font-weight="800">{spans}</text>
<text x="72" y="625" fill="#fff" fill-opacity=".72" font-family="Arial,Helvetica,sans-serif" font-size="21">INSIGHT FORGE · {date}</text>
</svg>""".format(
        a=a,
        b=b,
        category=html.escape(article["category"].upper()),
        spans=spans,
        date=article["date"],
    )

    path = "image/articles/" + article["slug"].replace(".html", "") + ".svg"
    write(path, svg)
    return path

def patch_article_html(article, image_path, keywords):
    path = article["url"]
    source = read(path)

    if "cite" in source:
        raise RuntimeError(path + " contains a raw citation token")

    body_text = re.sub(r"<[^>]+>", " ", source)
    word_count = len(re.findall(r"\b[\w'-]+\b", body_text, flags=re.UNICODE))
    if word_count < 650:
        raise RuntimeError(path + " is below the 650-word quality gate")

    source_links = re.findall(r'href=["\'](https?://[^"\']+)["\']', source, flags=re.I)
    source_domains = {domain(url) for url in source_links if domain(url)}
    if len(source_domains) < 2:
        raise RuntimeError(path + " must cite at least two independent source domains")

    image_url = BASE + image_path
    source = re.sub(
        r'(<img\b[^>]*\bsrc=["\'])[^"\']+(["\'])',
        lambda m: m.group(1) + image_path + m.group(2),
        source,
        count=1,
        flags=re.I,
    )

    keyword_tag = '<meta name="keywords" content="' + html.escape(", ".join(keywords), quote=True) + '">'
    if re.search(r'<meta\s+name=["\']keywords["\']', source, flags=re.I):
        source = re.sub(
            r'<meta\s+name=["\']keywords["\']\s+content=["\'][^"\']*["\']\s*/?>',
            keyword_tag,
            source,
            count=1,
            flags=re.I,
        )
    else:
        source = source.replace("</head>", keyword_tag + "</head>", 1)

    schema_match = re.search(
        r'<script\s+type=["\']application/ld\+json["\']>(.*?)</script>',
        source,
        flags=re.I | re.S,
    )
    if not schema_match:
        raise RuntimeError(path + " is missing Article structured data")

    try:
        schema = json.loads(schema_match.group(1))
    except json.JSONDecodeError as exc:
        raise RuntimeError(path + " has invalid JSON-LD: " + str(exc))

    schema["image"] = [image_url]
    schema["keywords"] = keywords
    schema["articleSection"] = article["category"]
    schema["author"] = {"@type": "Organization", "name": "Insight Forge"}
    schema["dateModified"] = article["date"]

    replacement = '<script type="application/ld+json">' + json.dumps(schema, ensure_ascii=False) + "</script>"
    source = source[:schema_match.start()] + replacement + source[schema_match.end():]
    write(path, source)
    return source_domains

def update_feed(items):
    path = "latest-news.json"
    write(path, json.dumps(items, ensure_ascii=False, indent=2) + "\n")

def write_social(today, articles):
    rows = []
    markdown = "# Insight Forge Social Copy — " + today + "\n\n"
    for article in articles:
        keywords = article["keywords"]
        hashtags = " ".join("#" + re.sub(r"[^A-Za-z0-9]", "", word) for word in keywords[:6])
        url = BASE + article["slug"] + ".html"

        x = (article["title"] + " — " + article["description"] + " " + url).strip()
        if len(x) > 260:
            x = article["title"][:150].rstrip() + " — " + url

        instagram = article["description"] + "\n\nRead: " + url + "\n\n" + hashtags
        reddit_title = article["title"]
        reddit_body = article["description"] + "\n\nWhat stands out from the latest reporting is covered in the full Insight Forge article."

        rows.append({
            "category": article["category"],
            "title": article["title"],
            "url": url,
            "x_post": x,
            "instagram_caption": instagram,
            "reddit_title": reddit_title,
            "reddit_body": reddit_body,
        })

        markdown += "## " + article["category"] + "\n\n"
        markdown += "**X:** " + x + "\n\n"
        markdown += "**Instagram:**\n" + instagram + "\n\n"
        markdown += "**Reddit title:** " + reddit_title + "\n\n"
        markdown += "**Reddit body:**\n" + reddit_body + "\n\n"

    payload = {"date": today, "site": "Insight Forge", "articles": rows}
    write("social-posts/" + today + ".json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    write("social-posts/" + today + ".md", markdown)

def rebuild_page_sitemap(new_articles):
    path = "page-sitemap.xml"
    source = read(path)
    urls = re.findall(r"<loc>\s*(https://[^<]+?)\s*</loc>", source)
    urls.extend(BASE + a["slug"] + ".html" for a in new_articles)

    out, seen = [], set()
    for url in urls:
        if url not in seen:
            seen.add(url)
            out.append(url)

    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for url in out:
        lines += [
            "  <url>",
            "    <loc>" + html.escape(url) + "</loc>",
            "    <priority>" + ("1.0" if url == BASE else "0.8") + "</priority>",
            "  </url>",
        ]
    lines.append("</urlset>")
    write(path, "\n".join(lines) + "\n")

def rebuild_image_sitemap(new_articles):
    path = "image-sitemap.xml"
    source = read(path)
    pairs = re.findall(
        r"<loc>\s*(https://[^<]+?)\s*</loc>\s*<image:image>\s*<image:loc>\s*(https://[^<]+?)\s*</image:loc>",
        source,
        flags=re.I | re.S,
    )

    mapping = {}
    for page_url, image_url in pairs:
        mapping.setdefault(page_url.strip(), image_url.strip())

    for article in new_articles:
        mapping[BASE + article["slug"] + ".html"] = BASE + article["image"]

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">',
    ]
    for page_url, image_url in mapping.items():
        lines += [
            "  <url>",
            "    <loc>" + html.escape(page_url) + "</loc>",
            "    <image:image>",
            "      <image:loc>" + html.escape(image_url) + "</image:loc>",
            "    </image:image>",
            "  </url>",
        ]
    lines.append("</urlset>")
    write(path, "\n".join(lines) + "\n")

def main():
    today = dt.datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%Y-%m-%d")
    data = json.loads(read("latest-news.json"))
    todays = [x for x in data if x.get("date") == today]

    if not todays:
        raise RuntimeError("No articles were published for " + today)

    existing = [x.get("title", "") for x in data if x not in todays]
    for item in todays:
        if max((title_similarity(item["title"], old) for old in existing), default=0) >= 0.78:
            raise RuntimeError("Near-duplicate title detected: " + item["title"])

    updated = []
    for item in data:
        item = dict(item)
        if item.get("date") == today:
            item["keywords"] = item.get("keywords") or extract_keywords(item)
            image_path = create_thumbnail(item)
            item["image"] = image_path
            item["alt"] = item.get("alt") or item["title"]
            item["description"] = item.get("description") or ""
            patch_article_html(item, image_path, item["keywords"])
        updated.append(item)

    update_feed(updated[:160])
    todays_final = [x for x in updated if x.get("date") == today]
    write_social(today, todays_final)
    rebuild_page_sitemap(todays_final)
    rebuild_image_sitemap(todays_final)

    print("QA/enhancement passed for", len(todays_final), "article(s)")
    print("Generated unique SVG thumbnails, verified source diversity, refreshed feed metadata, social copy, and both sitemaps.")

if __name__ == "__main__":
    main()
