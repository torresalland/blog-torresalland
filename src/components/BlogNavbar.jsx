import React from 'react';

export default function BlogNavbar({ onNavigateHome }) {
  const handleHome = (e) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
    e.preventDefault();
    onNavigateHome();
  };
  return (
    <header className="fixed top-0 left-0 right-0 z-50 glass-panel py-4 px-6">
      <nav aria-label="Principal" className="max-w-6xl mx-auto flex items-center justify-between gap-4">
        <a href="/" onClick={handleHome} className="flex items-center gap-3 min-w-0">
          <span aria-hidden="true" className="w-8 h-8 shrink-0 rounded-lg bg-accent-gold flex items-center justify-center font-bold text-[#1a1100]">Á</span>
          <span className="font-bold text-lg tracking-tight text-text-primary truncate">
            Állan Torres <span className="text-accent-gold font-normal ml-1 border-l border-white/10 pl-2">Blog</span>
          </span>
        </a>
        <div className="flex items-center gap-5 shrink-0">
          <a href="https://torresalland.cloud/" className="hidden sm:inline text-sm font-medium text-text-secondary hover:text-text-primary transition-colors">Site principal</a>
          <a href="https://torresalland.cloud/#contato" className="text-sm font-semibold text-[#1a1100] bg-accent-gold px-4 py-2 rounded-full hover:bg-[#FBBF24] transition-colors">
            Fale comigo
          </a>
        </div>
      </nav>
    </header>
  );
}
