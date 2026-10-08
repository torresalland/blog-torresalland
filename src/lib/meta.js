import { useEffect } from 'react';

const SITE = 'https://blog.torresalland.cloud';

function upsert(tag, selector, attrs, valueAttr, value) {
  let el = document.head.querySelector(selector);
  if (!el) {
    el = Object.assign(document.createElement(tag), attrs);
    document.head.appendChild(el);
  }
  el.setAttribute(valueAttr, value);
}

/** Atualiza title, description, canonical e robots durante a navegação SPA. */
export function useDocumentMeta({ title, description, path = '/', noindex = false }) {
  useEffect(() => {
    document.title = title;
    upsert('meta', 'meta[name="description"]', { name: 'description' }, 'content', description);
    upsert('link', 'link[rel="canonical"]', { rel: 'canonical' }, 'href', SITE + path);
    const robots = document.head.querySelector('meta[name="robots"]');
    if (noindex) {
      upsert('meta', 'meta[name="robots"]', { name: 'robots' }, 'content', 'noindex');
    } else if (robots) {
      robots.remove();
    }
  }, [title, description, path, noindex]);
}
