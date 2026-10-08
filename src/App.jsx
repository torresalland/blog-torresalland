import React, { useState, useEffect, useCallback } from 'react';
import BlogHome from './components/BlogHome';
import BlogPost from './components/BlogPost';
import BlogNavbar from './components/BlogNavbar';
import BlogFooter from './components/BlogFooter';

const ARTICLE_PATH = /^\/artigo\/([a-z0-9-]+)\/?$/i;
const slugFromPath = (p) => (p.match(ARTICLE_PATH) || [])[1] || null;

export default function App() {
  const [currentSlug, setCurrentSlug] = useState(() => slugFromPath(window.location.pathname));
  const [posts, setPosts] = useState([]);
  const [postsReady, setPostsReady] = useState(false);

  useEffect(() => {
    fetch('/blog/posts.json')
      .then((r) => (r.ok ? r.json() : { posts: [] }))
      .then((data) => setPosts(Array.isArray(data.posts) ? data.posts : []))
      .catch(() => setPosts([]))
      .finally(() => setPostsReady(true));
  }, []);

  useEffect(() => {
    const handlePop = () => setCurrentSlug(slugFromPath(window.location.pathname));
    window.addEventListener('popstate', handlePop);
    return () => window.removeEventListener('popstate', handlePop);
  }, []);

  const go = useCallback((path, slug) => {
    window.history.pushState({}, '', path);
    setCurrentSlug(slug);
    window.scrollTo({ top: 0 });
  }, []);

  const navigateToPost = useCallback((slug) => go(`/artigo/${slug}`, slug), [go]);
  const navigateHome = useCallback(() => go('/', null), [go]);

  return (
    <div className="min-h-screen font-sans relative">
      <a href="#conteudo" className="skip-link">Pular para o conteúdo</a>
      <BlogNavbar onNavigateHome={navigateHome} />
      <main id="conteudo" className="relative z-10 pt-28 pb-16 min-h-screen">
        {currentSlug ? (
          <BlogPost slug={currentSlug} posts={posts} onBack={navigateHome} onNavigate={navigateToPost} />
        ) : (
          <BlogHome posts={posts} ready={postsReady} onReadPost={navigateToPost} />
        )}
      </main>
      <BlogFooter />
    </div>
  );
}
