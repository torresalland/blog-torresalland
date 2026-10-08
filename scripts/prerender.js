import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distDir = path.resolve(__dirname, '../dist');
const blogContentDir = path.resolve(__dirname, '../public/blog');
const SITE = 'https://blog.torresalland.cloud';

const esc = (s) =>
  String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');

// JSON-LD dentro de <script>: impede fechamento antecipado da tag.
const jsonLd = (obj) => JSON.stringify(obj).replace(/</g, '\\u003c');

const isSlug = (s) => typeof s === 'string' && /^[a-z0-9-]+$/i.test(s);
const isIsoDate = (s) => typeof s === 'string' && /^\d{4}-\d{2}-\d{2}/.test(s) && !Number.isNaN(Date.parse(s));

const templatePath = path.join(distDir, 'index.html');
let template = '';
try {
  template = fs.readFileSync(templatePath, 'utf-8');
} catch {
  console.error("Erro: execute 'vite build' antes do prerender.");
  process.exit(1);
}

// 404 estático (o servidor responde 404 de verdade; ver public/.htaccess).
fs.writeFileSync(path.join(distDir, '404.html'), template);

const postsPath = path.join(blogContentDir, 'posts.json');
const posts = fs.existsSync(postsPath)
  ? (JSON.parse(fs.readFileSync(postsPath, 'utf-8')).posts || []).filter((p) => isSlug(p.slug))
  : [];

const sitemapUrls = [{ loc: `${SITE}/`, lastmod: null }];

for (const post of posts) {
  const url = `${SITE}/artigo/${post.slug}/`;
  const title = `${post.title} | Állan Torres`;
  const iso = isIsoDate(post.dateISO) ? post.dateISO : null;
  const image = typeof post.image === 'string' && /^https:\/\//.test(post.image) ? post.image : `${SITE}/og.jpg`;

  const head = [
    `<meta name="description" content="${esc(post.excerpt)}" />`,
    `<link rel="canonical" href="${url}" />`,
    `<meta property="og:title" content="${esc(post.title)}" />`,
    `<meta property="og:description" content="${esc(post.excerpt)}" />`,
    `<meta property="og:url" content="${url}" />`,
    `<meta property="og:image" content="${esc(image)}" />`,
    `<meta property="og:type" content="article" />`,
    iso ? `<meta property="article:published_time" content="${iso}" />` : '',
  ].filter(Boolean).join('\n    ');

  const ld = {
    '@context': 'https://schema.org',
    '@type': 'BlogPosting',
    headline: post.title,
    description: post.excerpt,
    image,
    mainEntityOfPage: url,
    author: { '@type': 'Person', name: post.author || 'Állan Torres', url: 'https://torresalland.cloud/' },
    publisher: { '@type': 'Person', name: 'Állan Torres' },
    inLanguage: 'pt-BR',
    ...(iso ? { datePublished: iso } : {}),
  };

  let html = template
    .replace(/<title>[\s\S]*?<\/title>/, `<title>${esc(title)}</title>`)
    .replace(/<meta name="description"[^>]*>/, '')
    .replace(/<link rel="canonical"[^>]*>/, '')
    .replace(/<meta property="og:(title|description|url|image|type)"[^>]*>\s*/g, '')
    .replace('</head>', `    ${head}\n    <script type="application/ld+json">${jsonLd(ld)}</script>\n  </head>`);

  const postDir = path.join(distDir, 'artigo', post.slug);
  fs.mkdirSync(postDir, { recursive: true });
  fs.writeFileSync(path.join(postDir, 'index.html'), html);
  sitemapUrls.push({ loc: url, lastmod: iso ? iso.slice(0, 10) : null });
  console.log(`Pré-renderizado (meta): /artigo/${post.slug}/`);
}

const sitemap =
  '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
  sitemapUrls
    .map((u) => `  <url><loc>${u.loc}</loc>${u.lastmod ? `<lastmod>${u.lastmod}</lastmod>` : ''}</url>`)
    .join('\n') +
  '\n</urlset>\n';
fs.writeFileSync(path.join(distDir, 'sitemap.xml'), sitemap);

console.log(`Pré-renderização concluída: ${posts.length} artigo(s), sitemap com ${sitemapUrls.length} URL(s).`);
