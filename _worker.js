const THEME_HREF = '/css/liquid-glass.css?v=1';

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
          element.append(`<link rel="stylesheet" href="${THEME_HREF}">`, { html: true });
        }
      })
      .on('html', {
        element(element) {
          element.setAttribute('data-insight-forge-theme', 'liquid-glass');
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
