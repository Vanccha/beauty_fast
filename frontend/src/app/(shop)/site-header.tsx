'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';

/**
 * Üst bar.
 *
 * Açılış sayfasında kahraman fotoğrafın ÜSTÜNE saydam olarak oturur —
 * fotoğraf ekranın en tepesinden başlar, site "beyaz bir çubukla"
 * değil görselle karşılar. Sayfa kaydırıldığında (veya başka bir
 * sayfaya geçildiğinde) opak zemine döner ki bağlantılar okunsun.
 *
 * Sunucu bileşeni olamaz: hem `usePathname` hem de kaydırma dinleyicisi
 * gerekiyor. Oturum bilgisi prop olarak sunucudan geçirilir.
 */
export function SiteHeader({
  salonName,
  customerName,
  links,
}: {
  salonName: string;
  customerName: string | null;
  links: { href: string; label: string }[];
}) {
  const pathname = usePathname();
  const isHome = pathname === '/';
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    if (!isHome) return;
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, [isHome]);

  // Saydam mod yalnızca ana sayfanın en tepesinde geçerlidir.
  const transparent = isHome && !scrolled;

  return (
    <header
      className={`z-30 transition-colors duration-300 ${
        isHome ? 'fixed inset-x-0 top-0' : 'sticky top-0 border-b border-sand-200'
      } ${transparent ? 'bg-transparent' : 'border-b border-sand-200 bg-sand-50/90 backdrop-blur'}`}
    >
      <div className="bleed flex items-center justify-between py-3">
        <Link href="/" className="flex items-center gap-2">
          <span
            className={`grid h-9 w-9 place-items-center rounded-xl text-sm font-semibold ${
              transparent ? 'bg-white/20 text-white backdrop-blur' : 'bg-plum-600 text-white'
            }`}
          >
            A
          </span>
          <span
            className={`display text-base ${transparent ? 'text-white drop-shadow' : 'text-ink-900'}`}
          >
            {salonName}
          </span>
        </Link>

        <nav className="hidden items-center gap-1 md:flex">
          {links.map((link) => {
            const active =
              link.href === '/' ? pathname === '/' : pathname.startsWith(link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? 'page' : undefined}
                className={`rounded-xl px-3 py-2 text-sm font-medium transition ${
                  transparent
                    ? 'text-white/85 hover:bg-white/15 hover:text-white'
                    : active
                      ? 'bg-sand-100 text-plum-700'
                      : 'text-ink-700 hover:bg-sand-100'
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex items-center gap-2">
          {customerName ? (
            <Link
              href="/hesabim"
              className={`hidden touch-target items-center rounded-xl px-4 text-sm font-semibold md:inline-flex ${
                transparent ? 'text-white hover:bg-white/15' : 'text-ink-700 hover:bg-sand-100'
              }`}
            >
              {customerName}
            </Link>
          ) : (
            <Link
              href="/giris"
              className={`hidden touch-target items-center rounded-xl px-4 text-sm font-semibold md:inline-flex ${
                transparent ? 'text-white hover:bg-white/15' : 'text-ink-700 hover:bg-sand-100'
              }`}
            >
              Üye Girişi
            </Link>
          )}

          <Link
            href="/randevu"
            className={`touch-target inline-flex items-center rounded-xl px-4 text-sm font-semibold transition active:scale-[0.98] ${
              transparent
                ? 'bg-white text-plum-700 hover:bg-plum-50'
                : 'bg-plum-600 text-white hover:bg-plum-700'
            }`}
          >
            Randevu al
          </Link>
        </div>
      </div>
    </header>
  );
}
