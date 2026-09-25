# Insight Forge live Trending setup

The site now includes a live engagement-based Trending API in `_worker.js`.

## What it tracks

For article URLs, the worker can collect:
- Page views
- Internal article clicks
- Clicks that came from the site's Search page

The ranking also applies an article-age/freshness signal, so new stories can surface while older high-engagement stories can continue to trend.

## Enable persistent global stats

The code checks for a Cloudflare Pages/Workers binding named:

`INSIGHT_STATS`

Create a **KV namespace** in Cloudflare and bind it to the deployed Pages project with the variable name `INSIGHT_STATS`.

In Cloudflare:
1. Open the Pages project for Insight Forge.
2. Open **Settings → Bindings** (or Functions/Workers bindings in the current dashboard UI).
3. Add a **KV namespace** binding.
4. Set the binding/variable name to `INSIGHT_STATS`.
5. Select the KV namespace created for Insight Forge.
6. Redeploy the project.

The site remains functional without the binding: `/api/trending` automatically falls back to a freshness-based ranking. Once the binding is present, the homepage ranking becomes engagement-driven.

## API endpoints

`POST /api/track`

Example payload:

```json
{"event":"click","url":"/example-article.html"}
```

Supported event values include `click`, `view`, and `search`.

`GET /api/trending`

Returns the current top five articles plus the engagement stats used by the ranking.

No IP address, account identity, or personal profile is stored by this implementation.
