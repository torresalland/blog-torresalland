import React from 'react';
import { ArrowRight, Sparkles, BookOpen } from 'lucide-react';

export default function BlogHome({ posts, onReadPost }) {
  if (!posts || posts.length === 0) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-24 text-center">
        <h2 className="text-3xl font-bold text-text-primary mb-4">Nenhum artigo publicado ainda</h2>
        <p className="text-text-secondary">Os artigos gerados pela IA aparecerão aqui em breve.</p>
      </div>
    );
  }

  // O post mais recente fica em destaque
  const featuredPost = posts[0];
  const otherPosts = posts.slice(1);

  return (
    <div className="max-w-6xl mx-auto px-6">
      <div className="text-center mb-16">
        <div className="inline-flex items-center justify-center p-3 rounded-2xl glass-panel mb-6 border border-white/10 shadow-[0_0_30px_rgba(56,189,248,0.15)]">
          <BookOpen className="w-6 h-6 text-accent-cyan" />
        </div>
        <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight text-text-primary mb-6">
          Insights & <span className="text-transparent bg-clip-text bg-gradient-to-r from-accent-cyan to-blue-500">Automação</span>
        </h1>
        <p className="text-lg text-text-secondary max-w-2xl mx-auto font-light">
          Artigos aprofundados sobre Inteligência Artificial, Automação de Processos, 
          SEO e Estratégias Digitais para alavancar seu negócio.
        </p>
      </div>

      {/* Post Destaque */}
      {featuredPost && (
        <div 
          onClick={() => onReadPost(featuredPost.slug)}
          className="group relative rounded-3xl overflow-hidden glass-panel border border-white/10 mb-16 cursor-pointer hover:border-accent-cyan/30 transition-all duration-500 flex flex-col md:flex-row shadow-2xl shadow-black/50"
        >
          {featuredPost.image ? (
            <div className="w-full md:w-1/2 overflow-hidden relative">
              <div className="absolute inset-0 bg-bg-dark/20 z-10 group-hover:bg-transparent transition-colors duration-500"></div>
              <img 
                src={featuredPost.image} 
                alt={featuredPost.title} 
                className="w-full h-full object-cover aspect-[4/3] md:aspect-auto group-hover:scale-105 transition-transform duration-700"
              />
            </div>
          ) : (
            <div className="w-full md:w-1/2 bg-gradient-to-br from-bg-card to-bg-dark flex items-center justify-center min-h-[300px]">
               <Sparkles className="w-16 h-16 text-accent-cyan/20" />
            </div>
          )}
          
          <div className="w-full md:w-1/2 p-8 md:p-12 flex flex-col justify-center relative">
            {/* Brilho sutil no hover */}
            <div className="absolute top-0 right-0 w-32 h-32 bg-accent-cyan/10 blur-[50px] opacity-0 group-hover:opacity-100 transition-opacity duration-500 rounded-full"></div>
            
            <div className="flex items-center gap-3 mb-6 relative z-10">
              <span className="text-xs font-bold uppercase tracking-wider text-accent-cyan px-3 py-1 rounded-full glass-panel border border-accent-cyan/20 shadow-[0_0_10px_rgba(56,189,248,0.2)]">
                {featuredPost.category}
              </span>
              <span className="text-sm text-text-muted">{featuredPost.date}</span>
            </div>
            
            <h2 className="text-3xl md:text-4xl font-bold text-text-primary mb-4 leading-tight group-hover:text-accent-cyan transition-colors relative z-10">
              {featuredPost.title}
            </h2>
            
            <p className="text-lg text-text-secondary font-light mb-8 line-clamp-3 relative z-10">
              {featuredPost.excerpt}
            </p>
            
            <div className="mt-auto flex items-center gap-2 text-text-primary font-semibold text-sm group-hover:text-accent-cyan transition-colors w-max relative z-10">
              Ler artigo completo <ArrowRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
            </div>
          </div>
        </div>
      )}

      {/* Grid de Outros Posts */}
      {otherPosts.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {otherPosts.map(post => (
            <div 
              key={post.slug} 
              onClick={() => onReadPost(post.slug)}
              className="group rounded-2xl glass-panel border border-white/5 hover:border-white/20 hover:bg-bg-card-hover transition-all duration-300 cursor-pointer flex flex-col overflow-hidden h-full"
            >
              {post.image && (
                <div className="w-full aspect-[16/9] overflow-hidden">
                  <img 
                    src={post.image} 
                    alt={post.title} 
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700 grayscale-[30%] group-hover:grayscale-0"
                  />
                </div>
              )}
              <div className="p-6 flex flex-col flex-grow">
                <div className="flex items-center justify-between mb-4">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-accent-gold">
                    {post.category}
                  </span>
                  <span className="text-xs text-text-muted">{post.date}</span>
                </div>
                
                <h3 className="text-xl font-bold text-text-primary mb-3 leading-snug group-hover:text-accent-gold transition-colors">
                  {post.title}
                </h3>
                
                <p className="text-sm text-text-secondary font-light line-clamp-3 mb-6 flex-grow">
                  {post.excerpt}
                </p>
                
                <div className="flex items-center gap-2 text-text-muted text-xs font-medium group-hover:text-text-primary transition-colors mt-auto">
                  Ler agora <ArrowRight className="w-3 h-3 group-hover:translate-x-1 transition-transform" />
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
