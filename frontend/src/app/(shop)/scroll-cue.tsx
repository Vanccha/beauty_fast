'use client';

import { ChevronDown } from 'lucide-react';
import { useEffect, useState } from 'react';

/**
 * "Aşağı kaydırın" ipucu: ilk ekran tam dolduğu için sayfanın devamı
 * görünmez; bu etiket kullanıcıya aşağıda içerik olduğunu söyler.
 * Yalnızca en üstteyken görünür, kaydırınca solar. Tıklanınca `targetId`
 * bölümüne kayar.
 */
export function ScrollCue({ targetId }: { targetId: string }) {
  const [atTop, setAtTop] = useState(true);

  useEffect(() => {
    const onScroll = () => setAtTop(window.scrollY < 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <button
      type="button"
      onClick={() => document.getElementById(targetId)?.scrollIntoView({ block: 'start' })}
      aria-hidden={!atTop}
      tabIndex={atTop ? 0 : -1}
      className={`absolute left-1/2 top-0 z-10 inline-flex -translate-x-1/2 -translate-y-1/2 items-center gap-1.5 whitespace-nowrap rounded-full border border-sand-200 bg-white px-4 py-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-ink-700 shadow-sm transition-opacity duration-300 hover:text-plum-600 ${
        atTop ? 'opacity-100' : 'pointer-events-none opacity-0'
      }`}
    >
      Aşağı kaydırın
      <ChevronDown size={14} strokeWidth={1.75} aria-hidden className="motion-safe:animate-bounce" />
    </button>
  );
}
