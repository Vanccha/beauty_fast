'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { CalendarSearch } from 'lucide-react';
import { useEffect, useState } from 'react';

import { SiteInstallButton } from '@/components/pwa/InstallButton';

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
      <div className="bleed flex h-16 items-center justify-between gap-4 md:h-[72px]">
        <Link href="/" className="flex min-w-0 items-baseline gap-2">
          <span
            className={`display truncate whitespace-nowrap text-lg sm:text-[22px] md:text-2xl ${transparent ? 'text-white' : 'text-ink-900'}`}
          >
            {salonName}
          </span>
        </Link>

        <nav className="hidden items-center gap-5 lg:flex xl:gap-7">
          {links.map((link) => {
            const active =
              link.href === '/' ? pathname === '/' : pathname === link.href || pathname.startsWith(`${link.href}/`);
            return (
              <Link
                key={link.href}
                href={link.href}
                aria-current={active ? 'page' : undefined}
                className={`whitespace-nowrap border-b py-1 text-xs font-semibold uppercase tracking-[0.14em] transition-colors ${
                  active ? 'border-brass-500' : 'border-transparent hover:border-brass-500'
                } ${
                  transparent
                    ? active
                      ? 'text-white'
                      : 'text-white/85 hover:text-white'
                    : active
                      ? 'text-ink-900'
                      : 'text-ink-700 hover:text-ink-900'
                }`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex shrink-0 items-center gap-1.5 md:gap-2">
          <SiteInstallButton transparent={transparent} />

          <Link
            href="/randevularim"
            aria-label="Randevu Sorgula"
            className={`touch-target hidden items-center justify-center gap-2 rounded-[2px] px-3 text-xs font-semibold uppercase tracking-[0.14em] whitespace-nowrap transition-colors md:inline-flex ${
              transparent ? 'text-white hover:bg-white/15' : 'text-ink-700 hover:bg-sand-100'
            }`}
          >
            <CalendarSearch size={18} strokeWidth={1.5} aria-hidden />
            <span className="hidden xl:inline">Randevu Sorgula</span>
          </Link>

          <Link href="/randevu" className={`btn-sm ${transparent ? 'btn-light' : 'btn-primary'}`}>
            Randevu Al
          </Link>
        </div>
      </div>
    </header>
  );
}
