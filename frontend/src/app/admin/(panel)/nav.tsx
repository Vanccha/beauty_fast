'use client';

import {
  BellRing,
  CalendarDays,
  ChevronDown,
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
 * Akordeon menü: bölümler alt alta dizilir; aktif bölümün içeriği
 * (`children`) kendi satırının hemen altında, sonraki satırın üstünde açılır.
 * `/admin` yalnızca kapalı listeyi gösterir. Açık satıra tekrar basmak
 * `/admin`e döner (kapanır).
 */
export function AdminAccordion({
  sections,
  children,
}: {
  sections: AdminSection[];
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const activeHref =
    sections.find((s) => pathname === s.href || pathname.startsWith(`${s.href}/`))?.href ?? null;

  const rowRefs = useRef<Record<string, HTMLAnchorElement | null>>({});
  const lastActive = useRef<string | null>(null);

  // Açık bölümün satırı üst barın hemen altında yapışık kalır; üst barın
  // yüksekliği (mobilde değişebilir) ölçülüp CSS değişkenine yazılır.
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

  // Yalnızca aktif bölüm DEĞİŞİNCE kaydır; bölüm içi gezinmede kullanıcıyı rahatsız etme.
  // Kapatınca (aktif yok) kapanan satır görünür alana getirilir: aşağıda
  // kaydırılmışken yapışık satırdan kapatan kullanıcı boşlukta kalmaz.
  useEffect(() => {
    const target = activeHref ?? lastActive.current;
    if (target && activeHref !== lastActive.current) {
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      rowRefs.current[target]?.scrollIntoView({
        behavior: reduce ? 'auto' : 'smooth',
        block: activeHref ? 'start' : 'nearest',
      });
    }
    lastActive.current = activeHref;
  }, [activeHref]);

  return (
    <ul className="admin-accordion">
      {sections.map((s) => {
        const open = s.href === activeHref;
        const Icon = ICONS[s.icon];
        return (
          <li key={s.href} className="admin-acc-item" data-open={open ? 'true' : undefined}>
            <Link
              href={open ? '/admin' : s.href}
              ref={(el) => {
                rowRefs.current[s.href] = el;
              }}
              aria-expanded={open}
              aria-current={open ? 'page' : undefined}
              className="admin-acc-row"
            >
              <span className="admin-acc-icon" aria-hidden>
                <Icon size={18} strokeWidth={1.5} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="admin-acc-label">{s.label}</span>
                <span className="admin-acc-desc">{s.desc}</span>
              </span>
              <ChevronDown size={18} strokeWidth={1.5} className="admin-acc-chevron" aria-hidden />
            </Link>
            {open && <div className="admin-acc-panel">{children}</div>}
          </li>
        );
      })}
    </ul>
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
