const THEME_HREF = '/css/liquid-glass.css?v=1';
const FAVICON_HREF = '/favicon.svg?v=1';
const SITE_NAME = 'Insight Forge';

function escapeAttr(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function extractMetaDescription(html) {
  const match = html.match(/<meta\s+[^>]*name=["']description["'][^>]*content=["']([^"']*)["'][^>]*>/i)
    || html.match(/<meta\s+[^>]*content=["']([^"']*)["'][^>]*name=["']description["'][^>]*>/i);
  return match ? match[1].trim() : '';
}

function extractMetaKeywords(html) {
  const match = html.match(/<meta\s+[^>]*name=["']keywords["'][^>]*content=["']([^"']*)["'][^>]*>/i)
    || html.match(/<meta\s+[^>]*content=["']([^"']*)["'][^>]*name=["']keywords["'][^>]*>/i);
  return match ? match[1].trim() : '';
}

export default {
  async fetch(request, env) {
    const response = await env.ASSETS.fetch(request);
    const contentType = response.headers.get('content-type') || '';

    if (!contentType.toLowerCase().includes('text/html')) {
      return response;
    }

    const url = new URL(request.url);
    const pathname = url.pathname;
    const isLikelyArticle = pathname.endsWith('.html') &&
      !/\/(index|search|anime|movies|tech|gaming|space-science|latest-news|about|contact|privacy-policy|faq)\.html$/i.test(pathname);

    let articleMeta = null;

    if (isLikelyArticle) {
      try {
        const feedResponse = await env.ASSETS.fetch(new Request(new URL('/latest-news.json', request.url)));
        if (feedResponse.ok) {
          const feed = await feedResponse.json();
          const normalizedPath = pathname.replace(/^\//, '');
          const item = Array.isArray(feed) ? feed.find(entry => entry && entry.url === normalizedPath) : null;

          if (item) {
            const articleResponse = response.clone();
            const articleHtml = await articleResponse.text();
            const description = extractMetaDescription(articleHtml) ||
              item.description ||
              item.alt ||
              `Read the latest ${item.category || 'Insight Forge'} story: ${item.title || ''}`;

            const image = item.image
              ? new URL(item.image.replace(/^\//, ''), url.origin + '/').href
              : new URL('/social-share.jpg', url.origin).href;

            const canonicalUrl = new URL(item.url.replace(/^\//, ''), url.origin + '/').href;

            articleMeta = {
              title: item.title || SITE_NAME,
              description,
              image,
              url: canonicalUrl,
              datePublished: item.date || '',
              category: item.category || ''
            };
          }
        }
      } catch (error) {
        articleMeta = null;
      }
    }

    const themed = new HTMLRewriter()
      .on('head', {
        element(element) {
          element.append(`<link rel="stylesheet" href="${THEME_HREF}"><link rel="icon" href="${FAVICON_HREF}" type="image/svg+xml" sizes="any">`, { html: true });

          if (articleMeta) {
            element.append(
              `<meta property="og:title" content="${escapeAttr(articleMeta.title)}">
<meta property="og:description" content="${escapeAttr(articleMeta.description)}">
<meta property="og:image" content="${escapeAttr(articleMeta.image)}">
<meta property="og:url" content="${escapeAttr(articleMeta.url)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="${SITE_NAME}">
${articleMeta.datePublished ? `<meta property="article:published_time" content="${escapeAttr(articleMeta.datePublished)}">` : ''}
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="${escapeAttr(articleMeta.title)}">
<meta name="twitter:description" content="${escapeAttr(articleMeta.description)}">
<meta name="twitter:image" content="${escapeAttr(articleMeta.image)}">
<meta name="twitter:url" content="${escapeAttr(articleMeta.url)}">`,
              { html: true }
            );
          }
        }
      })
      .on('html', {
        element(element) {
          element.setAttribute('data-insight-forge-theme', 'liquid-glass');
        }
      })
      .on('body', {
        element(element) {
          element.append(`<script>(function(){var navs=document.querySelectorAll('nav');navs.forEach(function(nav){var wrap=nav.querySelector('.nav-container')||nav;if(!wrap.querySelector('a[data-search-link]')){var s=document.createElement('a');s.href='search.html';s.textContent='🔍 Search';s.setAttribute('data-search-link','true');s.setAttribute('aria-label','Search Insight Forge');wrap.appendChild(s)}if(!wrap.querySelector('a[href*="faq.html"]')){var f=document.createElement('a');f.href='faq.html';f.textContent='FAQ';wrap.appendChild(f)}})})();</script>`, { html: true });
        }
      })
      .transform(response);

    const headers = new Headers(themed.headers);
    headers.set('Cache-Control', 'public, max-age=0, must-revalidate');
    return new Response(themed.body, {
      status: themed.status,
      statusText: themed.statusText,
      headers
    });
  }
};
