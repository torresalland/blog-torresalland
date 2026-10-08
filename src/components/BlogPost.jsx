import React, { useState, useEffect, useMemo } from 'react';
import { ArrowLeft, Share2, Linkedin, Check } from 'lucide-react';
import { useDocumentMeta } from '../lib/meta';
import { sanitizeArticle } from '../lib/sanitize';

export default function BlogPost({ slug, posts, onBack, onNavigate }) {
  const [postData, setPostData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/blog/content/${encodeURIComponent(slug)}.json`)
      .then((r) => {
        if (!r.ok) throw new Error('not-found');
        return r.json();
      })
      .then((data) => { if (!cancelled) { setPostData(data); setLoading(false); } })
      .catch(() => { if (!cancelled) { setPostData(null); setLoading(false); } });
    return () => { cancelled = true; };
  }, [slug]);

  useDocumentMeta(
    postData
      ? { title: `${postData.title} | Állan Torres`, description: postData.excerpt, path: `/artigo/${slug}/` }
      : { title: loading ? 'Carregando… | Állan Torres' : 'Artigo não encontrado | Állan Torres', description: 'Artigo não encontrado.', path: `/artigo/${slug}/`, noindex: !loading }
  );

  const html = useMemo(() => (postData ? sanitizeArticle(postData.contentHtml) : ''), [postData]);
  const related = useMemo(() => posts.filter((p) => p.slug !== slug).slice(0, 3), [posts, slug]);

  const handleShare = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard indisponível: sem feedback falso */
    }
  };

  const goBack = (e) => { e.preventDefault(); onBack(); };

  if (loading) {
    return <p role="status" className="max-w-4xl mx-auto px-6 py-24 text-center text-text-secondary">Carregando artigo…</p>;
  }

  if (!postData) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-12 text-center">
        <h1 className="text-4xl font-bold text-text-primary mb-4">Artigo não encontrado</h1>
        <a href="/" onClick={goBack} className="text-accent-gold hover:underline inline-flex items-center gap-2">
          <ArrowLeft aria-hidden="true" className="w-4 h-4" /> Voltar para o blog
        </a>
      </div>
    );
  }

  const shareUrl = `https://blog.torresalland.cloud/artigo/${slug}/`;

  return (
    <article className="max-w-3xl mx-auto px-6 py-12">
      <header className="mb-12">
        <a href="/" onClick={goBack} className="inline-flex items-center gap-2 text-text-secondary hover:text-text-primary transition-colors text-sm font-medium mb-10">
          <ArrowLeft aria-hidden="true" className="w-4 h-4" /> Voltar aos artigos
        </a>

        <div className="flex flex-wrap items-center gap-3 mb-6">
          <span className="text-xs font-bold uppercase tracking-widest text-accent-gold px-3 py-1 rounded-full border border-[var(--accent-gold-border)]">{postData.category}</span>
          <span className="text-sm text-text-secondary">{postData.date}</span>
          {postData.readTime && <span className="text-sm text-text-secondary">· {postData.readTime}</span>}
        </div>

        <h1 className="text-4xl md:text-5xl font-extrabold text-text-primary leading-tight mb-6 tracking-tight">{postData.title}</h1>
        <p className="text-xl text-text-secondary leading-relaxed mb-8">{postData.excerpt}</p>

        <div className="flex flex-col sm:flex-row items-center justify-between py-6 border-y border-border-subtle gap-4">
          <div className="flex items-center gap-4">
            <span aria-hidden="true" className="w-12 h-12 rounded-full bg-accent-gold flex items-center justify-center font-bold text-[#1a1100]">Á</span>
            <p className="font-semibold text-text-primary">{postData.author || 'Állan Torres'}</p>
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={handleShare} className="px-3 py-2.5 rounded-xl glass-panel text-text-secondary hover:text-text-primary transition-colors flex items-center gap-2 text-sm">
              {copied ? <Check aria-hidden="true" className="w-4 h-4" /> : <Share2 aria-hidden="true" className="w-4 h-4" />}
              <span role="status">{copied ? 'Link copiado' : 'Copiar link'}</span>
            </button>
            <a href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(shareUrl)}`} target="_blank" rel="noopener noreferrer" aria-label="Compartilhar no LinkedIn (abre em nova aba)" className="p-2.5 rounded-xl glass-panel text-text-secondary hover:text-text-primary transition-colors">
              <Linkedin aria-hidden="true" className="w-4 h-4" />
            </a>
          </div>
        </div>
      </header>

      {postData.image && (
        <figure className="mb-12 rounded-2xl overflow-hidden glass-panel p-1">
          <img src={postData.image} alt="" className="w-full h-auto aspect-video object-cover rounded-xl" />
        </figure>
      )}

      <div className="prose-blog" dangerouslySetInnerHTML={{ __html: html }} />

      {Array.isArray(postData.tags) && postData.tags.length > 0 && (
        <div className="mt-16 pt-8 border-t border-border-subtle">
          <h2 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">Tags</h2>
          <ul className="flex flex-wrap gap-2 list-none">
            {postData.tags.map((tag) => (
              <li key={tag} className="px-3 py-1 text-xs text-text-secondary glass-panel rounded-lg">#{tag}</li>
            ))}
          </ul>
        </div>
      )}

      {related.length > 0 && (
        <section className="mt-20" aria-labelledby="mais-artigos">
          <h2 id="mais-artigos" className="text-2xl font-bold text-text-primary mb-8 border-b border-border-subtle pb-4">Continue explorando</h2>
          <ul className="grid grid-cols-1 md:grid-cols-2 gap-6 list-none">
            {related.map((post) => (
              <li key={post.slug} className="flex">
                <a
                  href={`/artigo/${post.slug}`}
                  onClick={(e) => { if (e.metaKey || e.ctrlKey || e.shiftKey) return; e.preventDefault(); onNavigate(post.slug); }}
                  className="group p-6 rounded-2xl glass-panel glass-card flex flex-col w-full"
                >
                  <span className="text-[11px] font-bold uppercase tracking-wider text-accent-gold mb-3">{post.category}</span>
                  <h3 className="text-lg font-bold text-text-primary mb-2">{post.title}</h3>
                  <p className="text-sm text-text-secondary mt-auto">{post.excerpt}</p>
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </article>
  );
}
