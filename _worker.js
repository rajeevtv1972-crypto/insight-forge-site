const THEME_HREF = '/css/liquid-glass.css?v=1';
const FAVICON_HREF = '/favicon.svg?v=1';

export default {
  async fetch(request, env) {
    const response = await env.ASSETS.fetch(request);
    const contentType = response.headers.get('content-type') || '';

    if (!contentType.toLowerCase().includes('text/html')) {
      return response;
    }

    const themed = new HTMLRewriter()
      .on('head', {
        element(element) {
          element.append(`<link rel="stylesheet" href="${THEME_HREF}"><link rel="icon" href="${FAVICON_HREF}" type="image/svg+xml" sizes="any">`, { html: true });
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