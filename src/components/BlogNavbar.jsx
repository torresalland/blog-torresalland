import React from 'react';

export default function BlogNavbar({ onNavigateHome }) {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass-panel border-b border-white/5 py-4 px-6 shadow-xl shadow-black/20">
      <div className="max-w-6xl mx-auto flex items-center justify-between">
        <div 
          onClick={onNavigateHome}
          className="flex items-center gap-3 cursor-pointer group"
        >
          <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-accent-cyan to-blue-500 flex items-center justify-center font-bold text-white shadow-lg shadow-accent-cyan/20 group-hover:shadow-accent-cyan/40 transition-shadow">
            Á
          </div>
          <span className="font-bold text-lg tracking-tight text-text-primary">
            Állan Torres <span className="text-accent-cyan font-normal ml-1 border-l border-white/10 pl-2">Blog</span>
          </span>
        </div>
        
        <div className="flex items-center gap-6">
          <a href="https://torresalland.cloud" className="text-sm font-medium text-text-secondary hover:text-white transition-colors">Portfólio</a>
          <a href="https://wa.me/5584991875425?text=Ol%C3%A1%2C%20%C3%81llan.%20Vi%20um%20post%20no%20seu%20blog%20e%20gostaria%20de%20conversar%20com%20voc%C3%AA%20sobre%20isso." target="_blank" rel="noreferrer" className="text-sm font-semibold text-bg-dark bg-white px-4 py-2 rounded-full hover:bg-gray-200 transition-colors">
            Fale Comigo
          </a>
        </div>
      </div>
    </nav>
  );
}
