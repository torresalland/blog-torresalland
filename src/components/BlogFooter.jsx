import React from 'react';

export default function BlogFooter() {
  return (
    <footer className="border-t border-white/10 py-8 mt-12">
      <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4 text-sm text-text-secondary">
        <p>© {new Date().getFullYear()} Állan Torres. Todos os direitos reservados.</p>
        <nav aria-label="Rodapé" className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2">
          <a href="https://torresalland.cloud/" className="hover:text-text-primary transition-colors">Site principal</a>
          <a href="https://torresalland.cloud/privacidade/" className="hover:text-text-primary transition-colors">Privacidade</a>
        </nav>
      </div>
      <p className="max-w-6xl mx-auto px-6 mt-4 text-xs text-text-secondary text-center md:text-left">
        Conteúdo produzido com apoio de inteligência artificial. Os textos têm caráter informativo e não constituem consultoria específica.
      </p>
    </footer>
  );
}
