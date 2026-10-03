import { ExternalLink, TriangleAlert } from 'lucide-react';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { InstallButton } from '@/components/pwa/InstallButton';
import { PushBell } from '@/components/pwa/PushBell';
import { serverApi, type MeResponse, type SalonInfo } from '@/lib/server-api';
import { AdminSections, StaffLogout, type AdminSection } from './nav';
import type { MessagingStatus } from './whatsapp/whatsapp-connect';

export const dynamic = 'force-dynamic';

/** Ham rol kodu yerine insan okur etiket. */
const ROLE_LABEL: Record<string, string> = {
  OWNER: 'Salon sahibi',
  MANAGER: 'Yönetici',
  STAFF: 'Personel',
};

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

  const sections: AdminSection[] = [
    { href: '/admin/ozet', label: 'Genel Bakış', desc: 'Günün özeti ve uyarılar', icon: 'ozet' },
    { href: '/admin/takvim', label: 'Takvim', desc: 'Günlük randevu akışı', icon: 'takvim' },
    { href: '/admin/musteriler', label: 'Müşteriler', desc: 'Kayıtlar, notlar ve geçmiş', icon: 'musteriler' },
    { href: '/admin/stok', label: 'Stok', desc: 'Ürünler ve kritik seviyeler', icon: 'stok' },
    { href: '/admin/kampanyalar', label: 'Kampanyalar', desc: 'İndirim ve duyurular', icon: 'kampanyalar' },
    { href: '/admin/hatirlatmalar', label: 'Hatırlatmalar', desc: 'Randevu bildirimleri', icon: 'hatirlatmalar' },
    { href: '/admin/firsat-saatleri', label: 'Fırsat Saatleri', desc: 'Boş saatleri değerlendir', icon: 'firsat' },
    { href: '/admin/portfolyo', label: 'Portfolyo', desc: 'Çalışma fotoğrafları', icon: 'portfolyo' },
    { href: '/admin/yorumlar', label: 'Yorumlar', desc: 'Müşteri değerlendirmeleri', icon: 'yorumlar' },
    ...(isManager
      ? ([
          { href: '/admin/whatsapp', label: 'WhatsApp', desc: 'Bağlantı ve mesajlaşma', icon: 'whatsapp' },
        ] as AdminSection[])
      : []),
  ];

  return (
    <div className="admin-shell min-h-dvh bg-sand-50">
      <header data-admin-header className="sticky top-0 z-30 border-b border-sand-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between gap-3 px-4 py-2.5">
          <div className="min-w-0">
            <p className="eyebrow">Yönetim paneli</p>
            <p className="display truncate text-lg leading-tight">{branch.salon.name}</p>
            <p className="muted truncate !text-xs">
              {staff.name} · {ROLE_LABEL[staff.role] ?? staff.role}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <InstallButton />
            <PushBell />
            <Link href="/" className="btn-ghost btn-sm hidden md:inline-flex">
              Siteyi gör
              <ExternalLink size={14} strokeWidth={1.5} aria-hidden />
            </Link>
            <StaffLogout />
          </div>
        </div>
      </header>

      {whatsappDown && (
        <div className="border-b border-sand-200 bg-white">
          <p className="mx-auto flex max-w-7xl items-start gap-2.5 border-l-2 border-danger-600 px-4 py-2.5 text-sm text-ink-700">
            <TriangleAlert size={16} strokeWidth={1.5} className="mt-0.5 shrink-0 text-danger-600" aria-hidden />
            <span>
              WhatsApp bağlı değil: müşteriler giriş kodu alamıyor ve hatırlatmalar gönderilmiyor.{' '}
              <Link href="/admin/whatsapp" className="font-semibold text-plum-700 underline underline-offset-2">
                Bağlantıyı kur
              </Link>
            </span>
          </p>
        </div>
      )}

      <main className="mx-auto max-w-7xl px-3 pt-3 pb-[max(1rem,env(safe-area-inset-bottom))] md:px-4">
        <AdminSections sections={sections}>{children}</AdminSections>
      </main>
    </div>
  );
}
