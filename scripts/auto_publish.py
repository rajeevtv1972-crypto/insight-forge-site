#!/usr/bin/env python3
import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://insight-forge-site.pages.dev/"
GEMINI_MODELS = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.6-flash"]

GENRES = [
    {
        "name": "Technology",
        "page": "tech.html",
        "image": "image/latest-tech.svg",
        "query": "technology AI gadgets smartphones hardware cybersecurity September 2026",
        "tag": "Technology",
    },
    {
        "name": "Anime",
        "page": "anime.html",
        "image": "image/latest-anime.svg",
        "query": "anime manga season 2026 2027 Crunchyroll Japan anime news September 2026",
        "tag": "Anime",
    },
    {
        "name": "Movies",
        "page": "movies.html",
        "image": "image/latest-movies.svg",
        "query": "movies cinema Marvel MCU Netflix Hollywood upcoming films September 2026",
        "tag": "Movies",
    },
    {
        "name": "Gaming",
        "page": "gaming.html",
        "image": "image/latest-gaming.svg",
        "query": "video games PlayStation Xbox Nintendo PC gaming September 2026 releases",
        "tag": "Gaming",
    },
    {
        "name": "Space",
        "page": "space-science.html",
        "image": "image/latest-space.svg",
        "query": "NASA SpaceX ISRO astronomy JWST space science September 2026",
        "tag": "Space",
    },
]

def read_file(path):
    with open(os.path.join(ROOT, path), "r", encoding="utf-8") as f:
        return f.read()

def write_file(path, content):
    full = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(full) or ROOT, exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)

def fetch_rss(query):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": query,
        "hl": "en-US",
        "gl": "US",
        "ceid": "US:en",
    })
    req = urllib.request.Request(url, headers={"User-Agent": "InsightForgeBot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
    root = ET.fromstring(data)
    items = []
    for item in root.findall("./channel/item")[:8]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        desc = re.sub(r"<[^>]+>", " ", item.findtext("description") or "")
        desc = re.sub(r"\\s+", " ", html.unescape(desc)).strip()
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else ""
        if title:
            items.append({"title": title, "link": link, "date": pub, "source": source, "snippet": desc[:600]})
    return items

def call_gemini(prompt):
    """Call Gemini with retries and automatic model fallback."""
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.55,
            "maxOutputTokens": 24000,
            "responseMimeType": "application/json",
        },
    }

    last_error = None

    for model_index, model in enumerate(GEMINI_MODELS):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": os.environ["GEMINI_API_KEY"],
            },
            method="POST",
        )

        # Give each model three attempts for transient service/network errors.
        for attempt in range(1, 4):
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    payload = json.loads(r.read().decode("utf-8"))
                print(f"Gemini model {model} responded successfully.")
                try:
                    text = payload["candidates"][0]["content"]["parts"][0]["text"]
                except Exception:
                    raise RuntimeError(
                        "Gemini returned no usable content: " + json.dumps(payload)[:1500]
                    )
                return json.loads(text)

            except urllib.error.HTTPError as exc:
                details = exc.read().decode("utf-8", errors="replace")
                last_error = f"HTTP {exc.code}: {details[:800]}"

                # Authentication, bad-request, quota and other non-transient errors
                # should fail immediately instead of hiding the real problem.
                if exc.code not in (429, 500, 502, 503, 504):
                    raise RuntimeError("Gemini API request failed: " + last_error)

                if attempt < 3:
                    wait_seconds = 15 * (2 ** (attempt - 1))
                    print(
                        f"Gemini {model} temporarily unavailable (HTTP {exc.code}). "
                        f"Retry {attempt + 1}/3 in {wait_seconds}s..."
                    )
                    time.sleep(wait_seconds)

            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = str(exc)
                if attempt < 3:
                    wait_seconds = 15 * (2 ** (attempt - 1))
                    print(
                        f"Gemini {model} network error. "
                        f"Retry {attempt + 1}/3 in {wait_seconds}s..."
                    )
                    time.sleep(wait_seconds)

        if model_index < len(GEMINI_MODELS) - 1:
            next_model = GEMINI_MODELS[model_index + 1]
            print(f"Gemini {model} did not recover. Switching to fallback model {next_model}...")

    raise RuntimeError("All Gemini models failed. Last error: " + str(last_error))

def existing_articles():
    try:
        data = json.loads(read_file("latest-news.json"))
    except Exception:
        data = []
    titles = [x.get("title", "") for x in data]
    urls = [x.get("url", "") for x in data]
    return titles, urls, data

def build_prompt(feeds, existing_titles, today):
    feed_text = json.dumps(feeds, ensure_ascii=False)
    old = json.dumps(existing_titles[-120:], ensure_ascii=False)
    return f"""
You are the editorial engine for Insight Forge, a general-interest website covering Technology, Anime, Movies, Gaming and Space.

Today is {today}. Create exactly ONE genuinely timely article for EACH of these five genres:
Technology, Anime, Movies, Gaming, Space.

Use the supplied Google News RSS results as leads. Do not invent facts, dates, quotes, product specifications, release dates, or events that are not supported by the supplied material or by clearly established background knowledge. Prefer the newest credible story in each genre. If a lead is weak or duplicate, choose another lead from the supplied results.

Each article must:
- be at least 650 words and normally 750-1000 words
- have a useful, specific title, not clickbait
- be original and readable, not a list of copied headlines
- use short paragraphs and 2-4 <h2> subheadings
- include a concise opening paragraph
- include a final takeaway paragraph
- include a "Sources" section with ONLY the supplied source URLs relevant to that article
- never fabricate a source URL
- never claim that an unverified rumor is confirmed
- clearly distinguish confirmed information from reports/rumors when applicable
- be suitable for Google AdSense and a normal family audience
- use HTML only inside the body_html field; no markdown
- avoid repeating the exact same topic as an existing article

Existing article titles to avoid:
{old}

RSS leads:
{feed_text}

Return ONLY valid JSON matching this exact structure:
{{
  "articles": [
    {{
      "genre": "Technology|Anime|Movies|Gaming|Space",
      "title": "...",
      "slug": "lowercase-hyphenated-slug",
      "description": "150-160 character SEO description",
      "dek": "short subtitle",
      "body_html": "<p>...</p><h2>...</h2>...",
      "source_urls": ["https://..."]
    }}
  ]
}}

Exactly 5 objects, one per genre. Slugs must be unique and must not reuse an existing article slug.
"""

def validate_article(a):
    required = ["genre", "title", "slug", "description", "dek", "body_html", "source_urls"]
    if any(not a.get(k) for k in required):
        return False
    words = re.findall(r"\\b\\w+[\\w'-]*\\b", re.sub(r"<[^>]+>", " ", a["body_html"]))
    if len(words) < 500:
        return False
    if not re.match(r"^[a-z0-9]+(?:-[a-z0-9]+){2,80}$", a["slug"]):
        return False
    if a["genre"] not in [g["name"] for g in GENRES]:
        return False
    if not isinstance(a["source_urls"], list) or not a["source_urls"]:
        return False
    for u in a["source_urls"]:
        if not isinstance(u, str) or not u.startswith("http"):
            return False
    return True

def article_html(a, genre, today):
    canonical = BASE + a["slug"] + ".html"
    sources = "".join(
        f'<li><a href="{html.escape(u, quote=True)}" target="_blank" rel="noopener">Source {i}</a></li>'
        for i, u in enumerate(a["source_urls"], 1)
    )
    schema = {
        "@context": "https://schema.org",
        "@type": "NewsArticle",
        "headline": a["title"],
        "description": a["description"],
        "datePublished": today,
        "dateModified": today,
        "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
        "publisher": {"@type": "Organization", "name": "Insight Forge"},
    }
    nav = '<a href="index.html">Home</a> <a href="anime.html">Anime</a> <a href="movies.html">Movies</a> <a href="tech.html">Tech</a> <a href="space-science.html">Space</a> <a href="gaming.html">Gaming</a>'
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{html.escape(a["title"])} | Insight Forge</title>
<meta name="description" content="{html.escape(a["description"], quote=True)}">
<meta name="robots" content="max-image-preview:large">
<link rel="canonical" href="{canonical}">
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-3756147512527882" crossorigin="anonymous"></script>
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False)}</script>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;margin:0;background:#f8f9fa;color:#1f2937;line-height:1.75}}
header{{background:#0f172a;color:#fff;padding:48px 20px;text-align:center}}header h1{{max-width:900px;margin:0 auto 12px;font-size:clamp(2rem,5vw,3.5rem);line-height:1.1}}header p{{color:#cbd5e1;max-width:800px;margin:auto;font-size:1.05rem}}
nav{{background:#1e293b;text-align:center;padding:12px;position:sticky;top:0;z-index:5}}nav a{{color:#e2e8f0;margin:0 8px;text-decoration:none;font-weight:700}}
main{{max-width:900px;margin:30px auto;padding:0 20px}}article{{background:#fff;padding:clamp(22px,5vw,48px);border-radius:18px;box-shadow:0 8px 30px rgba(15,23,42,.08)}}article img{{width:100%;border-radius:16px;margin-bottom:22px}}h2{{margin-top:32px;color:#0f172a}}a{{color:#2563eb}}.ad{{margin:30px 0}}footer{{background:#020617;color:#94a3b8;text-align:center;padding:40px 20px;margin-top:60px}}
</style>
</head>
<body>
<header><h1>{html.escape(a["title"])}</h1><p>{html.escape(a["dek"])}</p></header>
<nav>{nav}</nav>
<main>
<img src="{genre["image"]}" alt="{html.escape(a["title"], quote=True)}" style="width:100%;border-radius:16px;margin:24px 0">
<article>
{a["body_html"]}
<div class="ad"><ins class="adsbygoogle" style="display:block;text-align:center" data-ad-layout="in-article" data-ad-format="fluid" data-ad-client="ca-pub-3756147512527882" data-ad-slot="7208765893"></ins><script>(adsbygoogle=window.adsbygoogle||[]).push({{}});</script></div>
<h2>Sources</h2><ul>{sources}</ul>
<div id="disqus_thread"></div>
<script>var disqus_config=function(){{this.page.url=window.location.href;this.page.identifier="{a["slug"]}";}};(function(){{var d=document,s=d.createElement('script');s.src='https://mytechblog-4.disqus.com/embed.js';s.setAttribute('data-timestamp',+new Date());(d.head||d.body).appendChild(s)}})();</script>
</article>
</main>
<footer>© 2026 Insight Forge</footer>
</body>
</html>
'''

def update_category_page(path, a, today):
    content = read_file(path)
    card = f'<article class="card"><span class="tag">{html.escape(next(x for x in GENRES if x["name"] == a["genre"])["tag"])} · {dt.datetime.strptime(today, "%Y-%m-%d").strftime("%b %d")}</span><a href="{a["slug"]}.html">{html.escape(a["title"])}</a></article>'
    marker = '<div class="article-grid">'
    if marker not in content:
        print(f"WARNING: could not update {path}: article-grid marker missing")
        return
    content = content.replace(marker, marker + card, 1)
    write_file(path, content)

def update_latest_feed(articles, today):
    path = "latest-news.json"
    data = json.loads(read_file(path))
    for a, g in [(a, next(x for x in GENRES if x["name"] == a["genre"])) for a in articles]:
        data.insert(0, {
            "title": a["title"],
            "category": a["genre"],
            "date": today,
            "url": a["slug"] + ".html",
            "image": g["image"],
            "alt": a["title"],
        })
    data = data[:120]
    write_file(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

def update_sitemap(articles):
    path = "page-sitemap.xml"
    content = read_file(path)
    new_urls = []
    for a in articles:
        url = BASE + a["slug"]
        if url not in content:
            new_urls.append(f"  <url><loc>{url}</loc><priority>0.8</priority></url>")
    if new_urls:
        content = content.replace("</urlset>", "\n  <!-- Auto-published -->\n" + "\n".join(new_urls) + "\n</urlset>")
        write_file(path, content)

def main():
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("GEMINI_API_KEY secret is required.", file=sys.stderr)
        sys.exit(2)

    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    titles, urls, _ = existing_articles()

    feeds = {}
    for g in GENRES:
        print("Fetching trends:", g["name"])
        try:
            feeds[g["name"]] = fetch_rss(g["query"])
        except Exception as e:
            print("RSS failed:", g["name"], e)
            feeds[g["name"]] = []

    prompt = build_prompt(feeds, titles, today)
    print("Generating five articles with Gemini...")
    result = call_gemini(prompt)
    articles = result.get("articles", [])

    if len(articles) != 5:
        raise RuntimeError(f"Expected 5 articles, got {len(articles)}")

    seen_genres = set()
    seen_slugs = set(urls)
    valid = []
    for a in articles:
        if a["genre"] in seen_genres or a["slug"] + ".html" in seen_slugs or not validate_article(a):
            raise RuntimeError("Generated article failed validation: " + json.dumps(a)[:1200])
        seen_genres.add(a["genre"])
        seen_slugs.add(a["slug"] + ".html")
        valid.append(a)

    if seen_genres != {g["name"] for g in GENRES}:
        raise RuntimeError("Not all five genres were generated.")

    for a in valid:
        g = next(x for x in GENRES if x["name"] == a["genre"])
        article_path = a["slug"] + ".html"
        write_file(article_path, article_html(a, g, today))
        update_category_page(g["page"], a, today)
        print("Published:", article_path)

    update_latest_feed(valid, today)
    update_sitemap(valid)
    print("DONE: 5 articles published for", today)

if __name__ == "__main__":
    main()
