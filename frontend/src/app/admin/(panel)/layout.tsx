import Link from 'next/link';
import { redirect } from 'next/navigation';

import { serverApi, type MeResponse, type SalonInfo } from '@/lib/server-api';
import { AdminNavLink, StaffLogout } from './nav';
import type { MessagingStatus } from './whatsapp/whatsapp-connect';

export const dynamic = 'force-dynamic';

/**
 * Panel kabuğu ve YETKİ KAPISI.
 *
 * Guard burada, tek noktada uygulanır: `(panel)` grubundaki her sayfa
 * otomatik olarak korunur. Tek tek sayfalara `requireStaff()` eklemek
 * unutmaya açık olurdu.
 */
export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  // Yetki kapısı: oturum FastAPI'den doğrulanır.
  const me = await serverApi<MeResponse>('/api/me');
  const staff = me.staff;
  if (!staff) redirect('/admin/giris');

  const showcase = await serverApi<{ salon: SalonInfo }>('/api/showcase');
  const branch = { salon: { name: showcase.salon.salonName } };
  const isManager = staff.role === 'OWNER' || staff.role === 'MANAGER';

  // WhatsApp koparsa müşteriler giriş kodu alamaz: her panel sayfasında
  // görünür bir uyarı gösterilir. Durum alınamazsa panel yine de açılır.
  let messaging: MessagingStatus | null = null;
  if (isManager) {
    messaging = await serverApi<MessagingStatus>('/api/admin/messaging/status').catch(() => null);
  }
  const whatsappDown = messaging?.driver === 'evolution' && !messaging.ready;

  const links = [
    { href: '/admin', label: 'Panel', icon: '📊' },
    { href: '/admin/takvim', label: 'Takvim', icon: '🗓️' },
    { href: '/admin/musteriler', label: 'Müşteriler', icon: '👥' },
    { href: '/admin/stok', label: 'Stok', icon: '📦' },
    { href: '/admin/kampanyalar', label: 'Kampanya', icon: '🎯' },
    { href: '/admin/hatirlatmalar', label: 'Hatırlatma', icon: '🔔' },
    { href: '/admin/firsat-saatleri', label: 'Fırsat', icon: '🔥' },
    { href: '/admin/portfolyo', label: 'Portfolyo', icon: '✨' },
    { href: '/admin/yorumlar', label: 'Yorumlar', icon: '⭐' },
    ...(isManager ? [{ href: '/admin/whatsapp', label: 'WhatsApp', icon: '💬' }] : []),
  ];

  return (
    <div className="min-h-dvh bg-sand-50">
      <header className="sticky top-0 z-30 border-b border-sand-200 bg-white">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{branch.salon.name}</p>
            <p className="muted">
              {staff.name} · {staff.role}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link href="/" className="btn-ghost hidden text-sm md:inline-flex">
              Siteyi gör
            </Link>
            <StaffLogout />
          </div>
        </div>

        <nav className="mx-auto max-w-7xl overflow-x-auto px-2 pb-2">
          <div className="flex gap-1">
            {links.map((l) => (
              <AdminNavLink key={l.href} href={l.href} icon={l.icon}>
                {l.label}
              </AdminNavLink>
            ))}
          </div>
        </nav>
      </header>

      {whatsappDown && (
        <div className="border-b border-rose-200 bg-rose-50">
          <p className="mx-auto max-w-7xl px-4 py-2 text-sm text-rose-700">
            WhatsApp bağlı değil: müşteriler giriş kodu alamıyor ve hatırlatmalar gönderilmiyor.{' '}
            <Link href="/admin/whatsapp" className="font-semibold underline">
              Bağlantıyı kur
            </Link>
          </p>
        </div>
      )}

      <main className="mx-auto max-w-7xl px-4 py-4">{children}</main>
    </div>
  );
}
