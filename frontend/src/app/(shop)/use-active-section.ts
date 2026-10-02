'use client';

import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';

/** Tek sayfa düzeninde izlenen bölüm kimlikleri (`/#portfolyo`, `/#yorumlar`, `/#ekip`). */
const SECTION_IDS = ['portfolyo', 'yorumlar', 'ekip'];

/** Bölümün "içinde" sayılması için sabit üst barın hemen altındaki çizgi (px). */
const OFFSET = 120;

/**
 * Ana sayfada şu an görünen bölümün kimliğini döndürür; hiçbiri değilse
 * `null` (yani "Ana Sayfa" aktif). Ana sayfa dışında her zaman `null`.
 * Bölüm elemanları henüz yoksa sessizce atlanır.
 */
export function useActiveSection(): string | null {
  const pathname = usePathname();
  const [active, setActive] = useState<string | null>(null);

  useEffect(() => {
    if (pathname !== '/') {
      setActive(null);
      return;
    }

    let frame = 0;
    const compute = () => {
      frame = 0;
      let next: string | null = null;
      for (const id of SECTION_IDS) {
        const el = document.getElementById(id);
        if (!el) continue;
        const rect = el.getBoundingClientRect();
        if (rect.top <= OFFSET && rect.bottom > OFFSET) next = id;
      }
      setActive(next);
    };
    const schedule = () => {
      if (!frame) frame = window.requestAnimationFrame(compute);
    };

    compute();
    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', schedule);
    window.addEventListener('hashchange', schedule);
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener('scroll', schedule);
      window.removeEventListener('resize', schedule);
      window.removeEventListener('hashchange', schedule);
    };
  }, [pathname]);

  return active;
}

/** Bağlantının aktif olup olmadığı — hash'li (`/#x`) ve düz bağlantılar için. */
export function isLinkActive(href: string, pathname: string, section: string | null): boolean {
  const hashIndex = href.indexOf('#');
  if (hashIndex !== -1) {
    return pathname === '/' && section === href.slice(hashIndex + 1);
  }
  if (href === '/') return pathname === '/' && section === null;
  return pathname === href || pathname.startsWith(`${href}/`);
}
