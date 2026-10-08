# blog-torresalland

Blog de artigos sobre automação, IA e presença web — `blog.torresalland.cloud`.
React 18 + Vite 8 + Tailwind 3. Mesmos tokens visuais do site principal (âmbar, vidro, Plus Jakarta Sans local).

## Comandos

```
npm ci
npm run dev
npm run build     # vite build + scripts/prerender.js (meta por artigo, 404.html, sitemap.xml)
```

## Formato dos artigos

- Índice: `public/blog/posts.json` → `{ "posts": [ { slug, title, excerpt, category, date, dateISO?, readTime?, author?, image? } ] }`.
  `slug` aceita só `[a-z0-9-]`. `dateISO` (AAAA-MM-DD) é opcional e alimenta `datePublished` no JSON-LD e no sitemap.
- Conteúdo: `public/blog/content/<slug>.json` com `contentHtml`, `tags?` e os mesmos campos do índice.
- O HTML do artigo é sanitizado com DOMPurify no navegador antes de renderizar.
- Rascunhos ou artigos retidos ficam fora de `public/` (ver `content-drafts/`). Só vai ao ar o que está em `public/blog/`.
- Afirmações numéricas, resultados ou casos reais só entram com fonte citada no próprio artigo.

## Limites conhecidos

- O corpo do artigo é carregado no navegador (JSON). O prerender grava apenas meta tags, canonical e JSON-LD; o texto depende de JavaScript.
- Imagens remotas (`https:`) são permitidas pela CSP; cada uma é uma requisição a terceiro. Prefira imagens próprias em `public/`.
- Cabeçalhos de `public/.htaccess` precisam ser conferidos em produção após o deploy aprovado.
