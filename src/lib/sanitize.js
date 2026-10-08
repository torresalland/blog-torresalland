import DOMPurify from 'dompurify';

// Artigos chegam como HTML gerado por automação: nada é confiável até passar por aqui.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'IMG') {
    if (!node.hasAttribute('alt')) node.setAttribute('alt', '');
    node.setAttribute('loading', 'lazy');
    node.setAttribute('referrerpolicy', 'no-referrer');
  }
  if (node.tagName === 'A' && node.getAttribute('href')) {
    node.setAttribute('rel', 'noopener noreferrer');
    if (/^https?:/i.test(node.getAttribute('href'))) node.setAttribute('target', '_blank');
  }
});

export function sanitizeArticle(html) {
  return DOMPurify.sanitize(String(html ?? ''), {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['style', 'form', 'input', 'button', 'iframe', 'object', 'embed'],
    FORBID_ATTR: ['style'],
  });
}
