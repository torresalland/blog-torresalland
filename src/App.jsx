import React, { useState, useEffect } from 'react';
import BlogHome from './components/BlogHome';
import BlogPost from './components/BlogPost';
import BlogNavbar from './components/BlogNavbar';
import BlogFooter from './components/BlogFooter';

export default function App() {
  const [currentSlug, setCurrentSlug] = useState(null);
  const [posts, setPosts] = useState([]);

  // Carrega o índice de posts ao iniciar
  useEffect(() => {
    fetch('/blog/posts.json?t=' + new Date().getTime())
      .then(r => r.json())
      .then(data => setPosts(data.posts || []))
      .catch(() => setPosts([]));
  }, []);

  // Verifica a URL inicial para deep-links diretos (ex: /artigo/slug)
  useEffect(() => {
    const path = window.location.pathname;
    const match = path.match(/^\/artigo\/(.+)/);
    if (match) setCurrentSlug(match[1]);

    const handlePop = () => {
      const p = window.location.pathname;
      const m = p.match(/^\/artigo\/(.+)/);
      setCurrentSlug(m ? m[1] : null);
    };
    window.addEventListener('popstate', handlePop);
    return () => window.removeEventListener('popstate', handlePop);
  }, []);

  const navigateToPost = (slug) => {
    window.history.pushState({}, '', `/artigo/${slug}`);
    setCurrentSlug(slug);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const navigateHome = () => {
    window.history.pushState({}, '', '/');
    setCurrentSlug(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="min-h-screen bg-bg-dark text-text-primary font-sans selection:bg-accent-cyan/30 relative">
      {/* Aurora Background orbes flutuantes - visual portfólio */}
      <div className="fixed inset-0 -z-10 overflow-hidden pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[500px] h-[500px] rounded-full bg-accent-cyan/8 blur-[130px] animate-float-1 mix-blend-screen" />
        <div className="absolute bottom-[10%] right-[-10%] w-[450px] h-[450px] rounded-full bg-accent-gold/6 blur-[140px] animate-float-2 mix-blend-screen" />
        <div className="absolute top-[40%] right-[15%] w-[350px] h-[350px] rounded-full bg-indigo-500/5 blur-[120px] animate-float-1 mix-blend-screen" />
      </div>

      <BlogNavbar onNavigateHome={navigateHome} />

      <main className="relative z-10 pt-24 pb-16 min-h-screen">
        {currentSlug ? (
          <BlogPost slug={currentSlug} posts={posts} onBack={navigateHome} onNavigate={navigateToPost} />
        ) : (
          <BlogHome posts={posts} onReadPost={navigateToPost} />
        )}
      </main>

      <BlogFooter />
    </div>
  );
}
