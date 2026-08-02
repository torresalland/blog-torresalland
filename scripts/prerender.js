import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const distDir = path.resolve(__dirname, '../dist');
const blogContentDir = path.resolve(__dirname, '../public/blog');

// Carrega o index.html gerado pelo Vite
const templatePath = path.join(distDir, 'index.html');
let template = '';
try {
  template = fs.readFileSync(templatePath, 'utf-8');
} catch (e) {
  console.error("Erro: Execute 'vite build' antes do prerender.");
  process.exit(1);
}

// 1. Resolve regras de roteamento SPA da Home e 404
fs.writeFileSync(path.join(distDir, '404.html'), template);

// 2. Lê os posts gerados
const postsPath = path.join(blogContentDir, 'posts.json');
if (fs.existsSync(postsPath)) {
  const postsData = JSON.parse(fs.readFileSync(postsPath, 'utf-8'));
  const posts = postsData.posts || [];

  // 3. Pré-renderiza rotas para cada artigo (para o Google ler as meta tags perfeitas)
  posts.forEach(post => {
    const postDir = path.join(distDir, 'artigo', post.slug);
    fs.mkdirSync(postDir, { recursive: true });

    // Injeta Meta Tags SEO para o Crawler do Google e Redes Sociais
    let seoTemplate = template
      .replace(
        '<title>Blog | Állan Torres — Automação, IA & Estratégia Digital</title>',
        `<title>${post.title} | Állan Torres</title>`
      )
      .replace(
        '<meta name="description" content="Artigos aprofundados sobre Automação, Inteligência Artificial, SEO & GEO escritos por Állan Torres. Conteúdo otimizado e gerado por IA." />',
        `<meta name="description" content="${post.excerpt}" />
    <!-- Open Graph SEO -->
    <meta property="og:title" content="${post.title}" />
    <meta property="og:description" content="${post.excerpt}" />
    <meta property="og:image" content="${post.image}" />
    <meta property="og:type" content="article" />
    <meta property="article:published_time" content="${post.date}" />`
      );

    // Salva o index.html da rota
    fs.writeFileSync(path.join(postDir, 'index.html'), seoTemplate);
    console.log(`✅ Pré-renderizado (SEO): /artigo/${post.slug}`);
  });
} else {
  console.log("Nenhum post encontrado para pré-renderizar.");
}

console.log("🚀 Pré-renderização SEO concluída com sucesso!");
