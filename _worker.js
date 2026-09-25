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

function escapeText(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function extractMeta(html, name) {
  const a = new RegExp('<meta\\s+[^>]*name=["\\']' + name + '["\\'][^>]*content=["\\']([^"\\']*)["\\'][^>]*>', 'i');
  const b = new RegExp('<meta\\s+[^>]*content=["\\']([^"\\']*)["\\'][^>]*name=["\\']' + name + '["\\'][^>]*>', 'i');
  return (html.match(a) || html.match(b) || [,''])[1].trim();
}

function normalize(value) {
  return String(value || '')
    .toLocaleLowerCase()
    .normalize('NFD')
    .replace(/[\\u0300-\\u036f]/g, '')
    .replace(/[^\\p{L}\\p{N}]+/gu, ' ')
    .trim();
}

function relatedStories(current, feed, keywords) {
  const currentTerms = new Set(
    normalize((keywords || '') + ' ' + (current?.title || '') + ' ' + (current?.category || ''))
      .split(/\\s+/)
      .filter(token => token.length > 2)
  );

  return feed
    .filter(item => item && item.url && item.url !== current.url)
    .map(item => {
      const itemTerms = new Set(
        normalize((item.title || '') + ' ' + (item.category || '') + ' ' + (item.keywords || '') + ' ' + (item.description || '') + ' ' + (item.alt || ''))
          .split(/\\s+/)
          .filter(token => token.length > 2)
      );

      let score = 0;
      if (item.category === current.category) score += 12;

      for (const term of currentTerms) {
        if (itemTerms.has(term)) score += 2;
      }

      const currentTitle = normalize(current.title);
      const itemTitle = normalize(item.title);
      const currentTitleTokens = currentTitle.split(/\\s+/).filter(t => t.length > 3);
      for (const token of currentTitleTokens) {
        if (itemTitle.includes(token)) score += 3;
      }

      return { item, score };
    })
    .filter(entry => entry.score > 0)
    .sort((a, b) => b.score - a.score || String(b.item.date).localeCompare(String(a.item.date)))
    .slice(0, 4)
    .map(entry => entry.item);
}

function relatedMarkup(items, url) {
  if (!items.length) return '';

  const cards = items.map(item => {
    const image = item.image
      ? new URL(item.image.replace(/^\\//, ''), url.origin + '/').href
      : new URL('/social-share.jpg', url.origin).href;

    return `
      <article class="if-related-card">
        <a href="/${escapeAttr(item.url)}">
          <img src="${escapeAttr(image)}" alt="${escapeAttr(item.alt || item.title)}" loading="lazy" decoding="async">
          <div class="if-related-body">
            <span class="if-related-cat">${escapeText(item.category || 'Insight Forge')}</span>
            <h3>${escapeText(item.title || 'Related story')}</h3>
            <span class="if-related-link">Read story →</span>
          </div>
        </a>
      </article>`;
  }).join('');

  return `
    <section class="if-related" aria-labelledby="if-related-title">
      <div class="if-related-head">
        <div>
          <span class="if-related-eyebrow">✦ Continue Reading</span>
          <h2 id="if-related-title">You might also like</h2>
          <p>More stories connected to this article.</p>
        </div>
        <a class="if-related-all" href="/latest-news.html">See all stories →</a>
      </div>
      <div class="if-related-grid">${cards}</div>
    </section>`;
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
      !/(^|\\/)(index|search|anime|movies|tech|gaming|space-science|latest-news|about|contact|privacy-policy|faq)\\.html$/i.test(pathname);

    let articleMeta = null;
    let relatedHtml = '';
    let articleHtml = '';

    if (isLikelyArticle) {
      try {
        const feedResponse = await env.ASSETS.fetch(new Request(new URL('/latest-news.json', request.url)));
        if (feedResponse.ok) {
          const feed = await feedResponse.json();
          const normalizedPath = pathname.replace(/^\\//, '');
          const item = Array.isArray(feed) ? feed.find(entry => entry && entry.url === normalizedPath) : null;

          if (item) {
            articleHtml = await response.clone().text();
            const description = extractMeta(articleHtml, 'description') ||
              item.description ||
              item.alt ||
              `Read the latest ${item.category || 'Insight Forge'} story: ${item.title || ''}`;

            const keywords = extractMeta(articleHtml, 'keywords') || item.keywords || '';

            const image = item.image
              ? new URL(item.image.replace(/^\\//, ''), url.origin + '/').href
              : new URL('/social-share.jpg', url.origin).href;

            const canonicalUrl = new URL(item.url.replace(/^\\//, ''), url.origin + '/').href;

            articleMeta = {
              title: item.title || SITE_NAME,
              description,
              image,
              url: canonicalUrl,
              datePublished: item.date || '',
              category: item.category || '',
              keywords
            };

            const related = relatedStories(articleMeta, Array.isArray(feed) ? feed : [], keywords);
            relatedHtml = relatedMarkup(related, url);
          }
        }
      } catch (error) {
        articleMeta = null;
        relatedHtml = '';
      }
    }


    function detectTopic(meta, sourceHtml) {
      const text = normalize((meta?.title || '') + ' ' + (meta?.description || '') + ' ' + (meta?.keywords || '') + ' ' + (sourceHtml || '').slice(0, 12000));
      const topics = [
        {name:'Marvel', patterns:['marvel','avengers','mcu','endgame','doomsday'], url:'/movies.html'},
        {name:'Dragon Ball', patterns:['dragon ball','beerus','goku','vegeta'], url:'/anime.html'},
        {name:'NASA', patterns:['nasa','space station','artemis','perseverance','hubble'], url:'/space-science.html'},
        {name:'Apple', patterns:['iphone','ipad','macbook','apple'], url:'/tech.html'},
        {name:'AI & Machine Learning', patterns:['artificial intelligence','machine learning','generative ai','ai model','ai compute','gemini','copilot'], url:'/tech.html'},
        {name:'PC & Gaming', patterns:['playstation','xbox','nintendo','pc gaming','steam'], url:'/gaming.html'}
      ];
      return topics.find(function(topic) {
        return topic.patterns.some(function(pattern) { return text.includes(pattern); });
      }) || null;
    }

    function buildBreadcrumbData(meta, topic, pageUrl) {
      const categoryMap = {Anime:'anime.html',Movies:'movies.html',Technology:'tech.html',Space:'space-science.html',Gaming:'gaming.html'};
      const list = [
        {'@type':'ListItem',position:1,name:'Home',item:new URL('/',pageUrl.origin).href},
        {'@type':'ListItem',position:2,name:meta.category || 'Stories',item:new URL(categoryMap[meta.category] || 'latest-news.html',pageUrl.origin + '/').href}
      ];
      if (topic) list.push({'@type':'ListItem',position:list.length + 1,name:topic.name,item:new URL(topic.url.replace(/^\//,''),pageUrl.origin + '/').href});
      list.push({'@type':'ListItem',position:list.length + 1,name:meta.title});
      return {'@context':'https://schema.org','@type':'BreadcrumbList',itemListElement:list};
    }

    const breadcrumbTopic = articleMeta ? detectTopic(articleMeta, articleHtml) : null;
    const breadcrumbData = articleMeta ? buildBreadcrumbData(articleMeta, breadcrumbTopic, url) : null;
    const breadcrumbStyles = articleMeta ? [
      '<style>',
      '.if-breadcrumb{max-width:1180px;margin:0 auto 18px;padding:11px 15px;border-radius:16px;background:rgba(255,255,255,.58);border:1px solid rgba(255,255,255,.74);box-shadow:0 8px 26px rgba(40,55,80,.07);backdrop-filter:blur(18px) saturate(140%);-webkit-backdrop-filter:blur(18px) saturate(140%);color:#667085;font-size:.78rem;line-height:1.4;overflow-x:auto;white-space:nowrap}',
      '.if-breadcrumb a{color:#245dc9 !important;font-weight:800}',
      '.if-breadcrumb .if-sep{margin:0 7px;color:#9aa4b5}',
      '.if-breadcrumb .if-current{color:#475467;font-weight:800}',
      '@media(max-width:720px){.if-breadcrumb{margin:0 0 14px;border-radius:14px;font-size:.75rem}}',
      '</style>'
    ].join('') : '';

    const breadcrumbMarkup = articleMeta ? [
      '<div class="if-breadcrumb" aria-label="Breadcrumb">',
      '<a href="/">Home</a><span class="if-sep" aria-hidden="true">→</span>',
      '<a href="/', escapeAttr(({'Anime':'anime.html','Movies':'movies.html','Technology':'tech.html','Space':'space-science.html','Gaming':'gaming.html'})[articleMeta.category] || 'latest-news.html'), '">',
      escapeText(articleMeta.category || 'Stories'), '</a>',
      breadcrumbTopic ? '<span class="if-sep" aria-hidden="true">→</span><a href="' + escapeAttr(breadcrumbTopic.url) + '">' + escapeText(breadcrumbTopic.name) + '</a>' : '',
      '<span class="if-sep" aria-hidden="true">→</span><span class="if-current">',
      escapeText(articleMeta.title), '</span></div>'
    ].join('') : '';

    const relatedStyles = relatedHtml ? `
<style>
.if-related{
  margin:48px 0 38px;
  padding:26px;
  border-radius:28px;
  background:linear-gradient(145deg,rgba(255,255,255,.78),rgba(255,255,255,.50));
  border:1px solid rgba(255,255,255,.84);
  box-shadow:0 18px 55px rgba(35,50,75,.10);
  backdrop-filter:blur(22px) saturate(140%);
  -webkit-backdrop-filter:blur(22px) saturate(140%);
}
.if-related-head{
  display:flex;
  justify-content:space-between;
  align-items:end;
  gap:16px;
  margin-bottom:18px;
}
.if-related-eyebrow{
  display:inline-flex;
  margin-bottom:7px;
  color:#245dc9;
  font-size:.72rem;
  font-weight:900;
  letter-spacing:.08em;
  text-transform:uppercase;
}
.if-related-head h2{
  margin:0;
  color:#172033;
  font-size:1.6rem;
  line-height:1.1;
  letter-spacing:-.03em;
}
.if-related-head p{
  margin:5px 0 0;
  color:#667085;
  font-size:.88rem;
}
.if-related-all{
  color:#2563eb !important;
  font-size:.84rem;
  font-weight:900;
  white-space:nowrap;
}
.if-related-grid{
  display:grid;
  grid-template-columns:repeat(4,minmax(0,1fr));
  gap:14px;
}
.if-related-card{
  overflow:hidden;
  border-radius:21px;
  background:rgba(255,255,255,.70);
  border:1px solid rgba(255,255,255,.82);
  box-shadow:0 11px 32px rgba(15,23,42,.07);
  transition:transform .22s ease,box-shadow .22s ease,border-color .22s ease;
}
.if-related-card:hover{
  transform:translateY(-4px);
  box-shadow:0 19px 42px rgba(15,23,42,.12);
  border-color:rgba(37,99,235,.24);
}
.if-related-card img{
  width:100%;
  aspect-ratio:16/9;
  display:block;
  object-fit:cover;
  background:#dbeafe;
  border-radius:0 !important;
  box-shadow:none !important;
}
.if-related-body{padding:14px 15px 16px}
.if-related-cat{
  display:inline-flex;
  margin-bottom:8px;
  padding:5px 8px;
  border-radius:999px;
  background:rgba(37,99,235,.09);
  color:#1d4ed8;
  font-size:.67rem;
  font-weight:900;
}
.if-related-card h3{
  margin:0;
  color:#1b2942;
  font-size:.98rem;
  line-height:1.3;
  letter-spacing:-.015em;
}
.if-related-link{
  display:inline-flex;
  margin-top:10px;
  color:#2563eb;
  font-size:.78rem;
  font-weight:900;
}
@media(max-width:950px){
  .if-related-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
}
@media(max-width:560px){
  .if-related{padding:19px;border-radius:23px;margin-top:38px}
  .if-related-head{align-items:flex-start;flex-direction:column}
  .if-related-grid{grid-template-columns:1fr}
}
@media(prefers-reduced-motion:reduce){
  .if-related-card{transition:none}
  .if-related-card:hover{transform:none}
}
</style>` : '';

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
<meta name="twitter:url" content="${escapeAttr(articleMeta.url)}">${breadcrumbStyles}${relatedStyles}${breadcrumbData ? '<script type="application/ld+json">' + JSON.stringify(breadcrumbData) + '</script>' : ''}`,
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
      .on('main img', {
        element(element) {
          if (articleMeta && !element.getAttribute('data-if-article-image')) {
            element.setAttribute('src', articleMeta.image);
            element.setAttribute('alt', articleMeta.title);
            element.setAttribute('loading', 'eager');
            element.setAttribute('decoding', 'async');
            element.setAttribute('data-if-article-image', 'true');
          }
        }
      })
      .on('main', {
        element(element) {
          if (breadcrumbMarkup) element.prepend(breadcrumbMarkup, { html: true });
        }
      })
      .on('div#disqus_thread', {
        element(element) {
          if (relatedHtml) {
            element.before(relatedHtml, { html: true });
          }
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
