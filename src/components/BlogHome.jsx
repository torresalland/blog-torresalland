import React from 'react';
import { ArrowRight, BookOpen } from 'lucide-react';
import { useDocumentMeta } from '../lib/meta';

function PostLink({ post, onReadPost, className, children }) {
  const handle = (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
    e.preventDefault();
    onReadPost(post.slug);
  };
  return (
    <a href={`/artigo/${post.slug}`} onClick={handle} className={className}>
      {children}
    </a>
  );
}

export default function BlogHome({ posts, ready, onReadPost }) {
  useDocumentMeta({
    title: 'Blog | Állan Torres — Automação, IA e Estratégia Digital',
    description: 'Artigos sobre automação de processos, inteligência artificial aplicada e presença web, por Állan Torres.',
    path: '/',
  });

  const [featured, ...others] = posts;

  return (
    <div className="max-w-6xl mx-auto px-6">
      <div className="text-center mb-16">
        <div className="inline-flex items-center justify-center p-3 rounded-2xl glass-panel mb-6">
          <BookOpen aria-hidden="true" className="w-6 h-6 text-accent-gold" />
        </div>
        <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight text-text-primary mb-6">
          Automação, IA e <span className="text-accent-gold">estratégia digital</span>
        </h1>
        <p className="text-lg text-text-secondary max-w-2xl mx-auto">
          Artigos sobre automação de processos, inteligência artificial aplicada e presença web para empresas.
        </p>
      </div>

      {!ready ? (
        <p role="status" className="text-center text-text-secondary">Carregando artigos…</p>
      ) : !featured ? (
        <div className="glass-panel rounded-3xl p-10 text-center max-w-2xl mx-auto">
          <h2 className="text-2xl font-bold text-text-primary mb-3">Os primeiros artigos estão a caminho</h2>
          <p className="text-text-secondary mb-6">Ainda não há artigos publicados. Enquanto isso, conheça o trabalho no site principal.</p>
          <a href="https://torresalland.cloud/" className="inline-flex items-center gap-2 font-semibold text-accent-gold hover:underline">
            Ir para o site principal <ArrowRight aria-hidden="true" className="w-4 h-4" />
          </a>
        </div>
      ) : (
        <>
          <PostLink post={featured} onReadPost={onReadPost} className="group glass-panel glass-card rounded-3xl overflow-hidden mb-16 flex flex-col md:flex-row">
            {featured.image && (
              <div className="w-full md:w-1/2 overflow-hidden">
                <img src={featured.image} alt="" className="w-full h-full object-cover aspect-[4/3] md:aspect-auto" />
              </div>
            )}
            <div className="w-full md:w-1/2 p-8 md:p-12 flex flex-col justify-center">
              <div className="flex flex-wrap items-center gap-3 mb-6">
                <span className="text-xs font-bold uppercase tracking-wider text-accent-gold px-3 py-1 rounded-full border border-[var(--accent-gold-border)]">{featured.category}</span>
                <span className="text-sm text-text-secondary">{featured.date}</span>
              </div>
              <h2 className="text-3xl md:text-4xl font-bold text-text-primary mb-4 leading-tight">{featured.title}</h2>
              <p className="text-lg text-text-secondary mb-8">{featured.excerpt}</p>
              <span className="mt-auto inline-flex items-center gap-2 text-accent-gold font-semibold text-sm">
                Ler artigo completo <ArrowRight aria-hidden="true" className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
              </span>
            </div>
          </PostLink>

          {others.length > 0 && (
            <ul className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 list-none">
              {others.map((post) => (
                <li key={post.slug} className="flex">
                  <PostLink post={post} onReadPost={onReadPost} className="group glass-panel glass-card rounded-2xl overflow-hidden flex flex-col w-full">
                    {post.image && (
                      <div className="w-full aspect-[16/9] overflow-hidden">
                        <img src={post.image} alt="" loading="lazy" className="w-full h-full object-cover" />
                      </div>
                    )}
                    <div className="p-6 flex flex-col flex-grow">
                      <div className="flex items-center justify-between mb-4">
                        <span className="text-[11px] font-bold uppercase tracking-wider text-accent-gold">{post.category}</span>
                        <span className="text-xs text-text-secondary">{post.date}</span>
                      </div>
                      <h3 className="text-xl font-bold text-text-primary mb-3 leading-snug">{post.title}</h3>
                      <p className="text-sm text-text-secondary mb-6 flex-grow">{post.excerpt}</p>
                      <span className="inline-flex items-center gap-2 text-text-secondary text-xs font-medium mt-auto group-hover:text-text-primary transition-colors">
                        Ler agora <ArrowRight aria-hidden="true" className="w-3 h-3" />
                      </span>
                    </div>
                  </PostLink>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}
