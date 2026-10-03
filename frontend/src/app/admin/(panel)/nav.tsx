'use client';

import {
  BellRing,
  CalendarDays,
  ChevronLeft,
  Images,
  LayoutDashboard,
  LogOut,
  MessageCircle,
  Megaphone,
  Package,
  Star,
  Users,
  Zap,
  type LucideIcon,
} from 'lucide-react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useRef } from 'react';

import { apiSend } from '@/lib/api-client';

/** Sunucu bileşeninden fonksiyon geçirilemez; ikonlar anahtarla seçilir. */
const ICONS: Record<string, LucideIcon> = {
  ozet: LayoutDashboard,
  takvim: CalendarDays,
  musteriler: Users,
  stok: Package,
  kampanyalar: Megaphone,
  hatirlatmalar: BellRing,
  firsat: Zap,
  portfolyo: Images,
  yorumlar: Star,
  whatsapp: MessageCircle,
};

export interface AdminSection {
  href: string;
  label: string;
  desc: string;
  icon: keyof typeof ICONS;
}

/**
 * Bölüm menüsü: `/admin`de bölümler ekrana sığan bir karo ızgarasıdır
 * (mobilde 2 sütun, geniş ekranda 3-5). Karoya basınca bölüme girilir: ızgara
 * gizlenir, üst barın hemen altında yapışık ince bir çubuk ("‹ Menü" + bölüm
 * adı) görünür ve bölüm sayfası (`children`) tam genişlikte altında açılır.
 * Çıkış için "‹ Menü" bağlantısı `/admin`e döner; sayfa başına kaydırılır.
 */
export function AdminSections({
  sections,
  children,
}: {
  sections: AdminSection[];
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const active =
    sections.find((s) => pathname === s.href || pathname.startsWith(`${s.href}/`)) ?? null;
  const activeHref = active?.href ?? null;
  const lastActive = useRef<string | null | undefined>(undefined);

  // Üst barın yüksekliği (mobilde değişebilir) ölçülüp CSS değişkenine yazılır:
  // yapışık çubuk ve ızgara yüksekliği buna göre hesaplanır.
  useEffect(() => {
    const header = document.querySelector<HTMLElement>('[data-admin-header]');
    if (!header) return;
    const sync = () =>
      document.documentElement.style.setProperty('--admin-header-h', `${header.offsetHeight}px`);
    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(header);
    return () => observer.disconnect();
  }, []);

  // Yalnızca aktif bölüm DEĞİŞİNCE (girerken ve dönerken) en üste kaydır;
  // bölüm içi gezinmede kullanıcıyı rahatsız etme.
  useEffect(() => {
    if (lastActive.current !== undefined && lastActive.current !== activeHref) {
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      window.scrollTo({ top: 0, behavior: reduce ? 'auto' : 'smooth' });
    }
    lastActive.current = activeHref;
  }, [activeHref]);

  if (active) {
    const Icon = ICONS[active.icon];
    // Bölüm alt sayfalarının (ör. müşteri detayı) kendi h1'i olabilir: çift h1 olmasın.
    const isRoot = pathname === active.href;
    const Title = isRoot ? 'h1' : 'p';
    return (
      <>
        <div
          className="sticky z-20 -mx-3 flex items-center gap-2 border-b border-sand-200 bg-white/95 px-3 py-1.5 backdrop-blur md:-mx-4 md:px-4"
          style={{ top: 'var(--admin-header-h, 4.75rem)' }}
        >
          <Link
            href="/admin"
            aria-label="Menüye dön"
            className="-ml-1 inline-flex min-h-11 items-center gap-0.5 rounded-full py-1 pr-4 pl-2 text-sm font-semibold text-plum-700 no-underline transition hover:bg-plum-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum-600 active:scale-[0.98]"
          >
            <ChevronLeft size={20} strokeWidth={1.75} aria-hidden />
            Menü
          </Link>
          <span className="inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-plum-50 text-plum-700" aria-hidden>
            <Icon size={16} strokeWidth={1.5} />
          </span>
          <Title className="display m-0 min-w-0 truncate text-base font-semibold">{active.label}</Title>
        </div>
        <div className="min-w-0 overflow-x-auto pt-3 md:pt-4">{children}</div>
      </>
    );
  }

  return (
    <nav aria-label="Yönetim bölümleri">
      <ul className="m-0 grid list-none grid-cols-2 gap-3 p-0 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
        {sections.map((s) => {
          const Icon = ICONS[s.icon];
          return (
            <li key={s.href} className="flex min-w-0">
              <Link
                href={s.href}
                className="flex min-h-[max(92px,calc((100dvh-var(--admin-header-h,4.75rem)-4.75rem)/5))] w-full min-w-0 flex-col items-center justify-center gap-2 rounded-2xl border border-sand-200 bg-white p-3 text-center text-ink-900 no-underline transition hover:border-plum-300 hover:bg-plum-50/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum-600 active:scale-[0.98] active:border-plum-300 active:bg-plum-50/40 sm:min-h-36"
              >
                <span className="inline-flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-plum-50 text-plum-700" aria-hidden>
                  <Icon size={26} strokeWidth={1.5} />
                </span>
                <span className="display block w-full truncate text-base font-semibold leading-tight sm:text-lg">
                  {s.label}
                </span>
                <span className="muted line-clamp-2 hidden w-full !text-xs leading-snug min-[380px]:block">
                  {s.desc}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

export function StaffLogout() {
  const router = useRouter();
  return (
    <button
      type="button"
      className="btn-secondary btn-sm"
      onClick={async () => {
        await apiSend('/api/auth/logout', 'POST', { scope: 'staff' }).catch(() => undefined);
        router.push('/admin/giris');
        router.refresh();
      }}
    >
      <LogOut size={14} strokeWidth={1.5} aria-hidden />
      Çıkış
    </button>
  );
}
