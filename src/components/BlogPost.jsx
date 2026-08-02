import React from 'react';
import { ArrowLeft, Share2, Linkedin, Twitter, Check } from 'lucide-react';

export default function BlogPost({ slug, posts, onBack, onNavigate }) {
  const [postData, setPostData] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [copied, setCopied] = React.useState(false);

  React.useEffect(() => {
    setLoading(true);
    fetch(`/blog/content/${slug}.json`)
      .then(r => {
        if (!r.ok) throw new Error('Not found');
        return r.json();
      })
      .then(data => {
        setPostData(data);
        setLoading(false);
      })
      .catch(() => {
        setPostData(null);
        setLoading(false);
      });
  }, [slug]);

  // Encontra posts relacionados
  const relatedPosts = posts
    .filter(p => p.slug !== slug)
    .sort(() => 0.5 - Math.random())
    .slice(0, 3);

  const handleShare = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-12 flex flex-col items-center justify-center min-h-[50vh]">
        <div className="w-10 h-10 border-2 border-accent-gold/20 border-t-accent-gold rounded-full animate-spin mb-4" />
        <p className="text-text-secondary animate-pulse text-sm">Carregando conteúdo premium...</p>
      </div>
    );
  }

  if (!postData) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-12 text-center">
        <h1 className="text-4xl font-bold text-text-primary mb-4">Artigo não encontrado</h1>
        <button onClick={onBack} className="text-accent-cyan hover:underline inline-flex items-center gap-2">
          <ArrowLeft className="w-4 h-4" /> Voltar para o blog
        </button>
      </div>
    );
  }

  return (
    <article className="max-w-3xl mx-auto px-6 py-12">
      {/* Header do Post */}
      <header className="mb-12">
        <button 
          onClick={onBack}
          className="group flex items-center gap-2 text-text-secondary hover:text-text-primary transition-colors text-sm font-medium mb-10"
        >
          <div className="p-2 rounded-full glass-panel group-hover:bg-white/10 transition-colors">
            <ArrowLeft className="w-4 h-4" />
          </div>
          Voltar aos artigos
        </button>

        <div className="flex items-center gap-3 mb-6">
          <span className="text-xs font-bold uppercase tracking-widest text-accent-gold px-3 py-1 rounded-full glass-panel">
            {postData.category}
          </span>
          <span className="text-sm text-text-muted">{postData.date}</span>
          <span className="text-sm text-text-muted">•</span>
          <span className="text-sm text-text-muted">{postData.readTime}</span>
        </div>

        <h1 className="text-4xl md:text-5xl font-extrabold text-text-primary leading-tight mb-6 tracking-tight">
          {postData.title}
        </h1>

        <p className="text-xl text-text-secondary leading-relaxed mb-8 font-light">
          {postData.excerpt}
        </p>

        {/* Autor & Compartilhamento */}
        <div className="flex flex-col sm:flex-row items-center justify-between py-6 border-y border-border-subtle gap-4">
          <div className="flex items-center gap-4">
            <img 
              src={postData.authorImage || "https://github.com/torresalland.png"} 
              alt={postData.author} 
              className="w-12 h-12 rounded-full border-2 border-accent-cyan/20"
            />
            <div>
              <p className="font-semibold text-text-primary">{postData.author}</p>
              <p className="text-xs text-text-muted">Especialista em Automação & IA</p>
            </div>
          </div>

          <div className="flex gap-2">
            <button onClick={handleShare} className="p-2.5 rounded-xl glass-panel hover:bg-white/10 text-text-secondary hover:text-accent-cyan transition-all flex items-center gap-2 text-sm" title="Copiar Link">
              {copied ? <Check className="w-4 h-4 text-green-400" /> : <Share2 className="w-4 h-4" />}
              <span className="hidden sm:inline">{copied ? 'Copiado!' : 'Compartilhar'}</span>
            </button>
            <a href={`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(window.location.href)}`} target="_blank" rel="noreferrer" className="p-2.5 rounded-xl glass-panel hover:bg-[#0a66c2]/20 text-text-secondary hover:text-[#0a66c2] transition-all">
              <Linkedin className="w-4 h-4" />
            </a>
          </div>
        </div>
      </header>

      {/* Hero Image (se houver) */}
      {postData.image && (
        <figure className="mb-12 rounded-2xl overflow-hidden glass-panel border-white/10 p-1 relative group">
          <div className="absolute inset-0 bg-gradient-to-t from-bg-dark to-transparent opacity-60 z-10"></div>
          <img 
            src={postData.image} 
            alt={postData.title} 
            className="w-full h-auto aspect-video object-cover rounded-xl group-hover:scale-105 transition-transform duration-700"
          />
        </figure>
      )}

      {/* Conteúdo Renderizado (Markdown to HTML inserido via dangerouslySetInnerHTML) */}
      <div 
        className="prose-blog"
        dangerouslySetInnerHTML={{ __html: postData.contentHtml }}
      />

      {/* Footer do Artigo / Tags */}
      {postData.tags && postData.tags.length > 0 && (
        <div className="mt-16 pt-8 border-t border-border-subtle">
          <h4 className="text-sm font-semibold text-text-primary mb-4 uppercase tracking-wider">Tags</h4>
          <div className="flex flex-wrap gap-2">
            {postData.tags.map(tag => (
              <span key={tag} className="px-3 py-1 text-xs text-text-secondary glass-panel rounded-lg hover:text-accent-gold cursor-pointer transition-colors">
                #{tag}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Artigos Relacionados */}
      {relatedPosts.length > 0 && (
        <div className="mt-20">
          <h3 className="text-2xl font-bold text-text-primary mb-8 border-b border-border-subtle pb-4">
            Continue Explorando
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {relatedPosts.map(post => (
              <div 
                key={post.slug} 
                onClick={() => onNavigate(post.slug)}
                className="group p-6 rounded-2xl glass-panel hover:border-white/20 hover:bg-bg-card-hover transition-all cursor-pointer flex flex-col h-full"
              >
                <div className="flex items-center gap-3 mb-4">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-accent-cyan px-2 py-1 rounded-md bg-accent-cyan/10">
                    {post.category}
                  </span>
                  <span className="text-xs text-text-muted">{post.date}</span>
                </div>
                <h4 className="text-lg font-bold text-text-primary mb-2 group-hover:text-accent-cyan transition-colors line-clamp-2">
                  {post.title}
                </h4>
                <p className="text-sm text-text-secondary line-clamp-2 font-light mt-auto">
                  {post.excerpt}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </article>
  );
}
