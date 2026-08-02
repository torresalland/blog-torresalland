import React from 'react';

export default function BlogFooter() {
  return (
    <footer className="border-t border-white/5 py-8 mt-12 bg-bg-dark/50 backdrop-blur-md">
      <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
        <p className="text-sm text-text-muted">
          © {new Date().getFullYear()} Állan Torres. Todos os direitos reservados.
        </p>
        <p className="text-xs text-text-muted flex items-center gap-1">
          Criado com <span className="text-accent-cyan">Inteligência Artificial</span> e <span className="text-accent-gold">Automação</span>.
        </p>
      </div>
    </footer>
  );
}
