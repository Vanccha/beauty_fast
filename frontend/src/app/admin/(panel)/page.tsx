import Link from 'next/link';

import { formatTl } from '@/lib/api-client';
import { serverApi } from '@/lib/server-api';
import { formatDateTr, minutesToLabel } from '@/lib/time';

export const dynamic = 'force-dynamic';

interface DashboardAppointment {
  id: number;
  startMin: number;
  endMin: number;
  status: string;
  isOpportunity: boolean;
  shadowParentId: number | null;
  customerId: number;
  customer: { firstName: string; lastName: string | null; tier: string };
  staffName: string;
  services: string[];
  allergies: { label: string; severity: string }[];
  risk: { score: number; label: string } | null;
  totalPrice: number;
}

interface DashboardResponse {
  date: string;
  dateLabel: string;
  appointments: DashboardAppointment[];
  criticalStock: {
    id: number;
    name: string;
    quantity: number;
    unit: string;
    criticalLevel: number;
    severity: 'OUT' | 'LOW';
  }[];
  pendingNotifications: number;
  week: { completed: number; revenue: number };
}

/**
 * ====================================================================
 * PANEL — günün özeti
 * ====================================================================
 *
 * Üç soruyu yanıtlar: bugün ne var, neyi gözden kaçırıyorum, neyi
 * ısmarlamam gerek.
 *
 * "Riskli randevular" bölümü çapraz-salon skorunu KULLANIR ama yalnızca
 * bugünün randevuları için sorgular (25 müşteri × hash sorgusu yerine
 * ~5 sorgu). KVKK: yalnızca skor/etiket gösterilir, başka salonun adı
 * veya randevu detayı gösterilmez.
 */
export default async function AdminDashboard() {
  // Veri FastAPI backend'inden gelir; bu sayfa veritabanını bilmez.
  const data = await serverApi<DashboardResponse>('/api/admin/dashboard');

  const todayKey = data.date;
  const today = data.appointments;
  const critical = data.criticalStock;
  const pendingNotifications = data.pendingNotifications;
  const weekRevenue = { _count: data.week.completed, _sum: { totalPrice: data.week.revenue } };

  // Risk eşiği 45: bu skorun üstü "ön ödeme istenebilir" demektir.
  const risky = today.filter((a) => (a.risk?.score ?? 0) >= 45);
  const revenue = data.week.revenue;

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Bugünkü randevu" value={String(today.length)} />
        <Stat
          label="Tamamlanan (7 gün)"
          value={String(weekRevenue._count)}
          sub={formatTl(revenue)}
        />
        <Stat
          label="Kritik stok"
          value={String(critical.length)}
          tone={critical.length > 0 ? 'danger' : undefined}
        />
        <Stat
          label="Bekleyen bildirim"
          value={String(pendingNotifications)}
          tone={pendingNotifications > 0 ? 'warn' : undefined}
        />
      </div>

      {/* ---------------- Kritik stok ---------------- */}
      {critical.length > 0 && (
        <section className="rounded-2xl border-2 border-rose-300 bg-rose-50 p-4">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-rose-800">⚠️ Kritik stok uyarısı</h2>
            <Link href="/admin/stok" className="text-sm font-medium text-rose-800 underline">
              Stoğa git
            </Link>
          </div>
          <ul className="mt-2 space-y-1 text-sm text-rose-700">
            {critical.map((item) => (
              <li key={item.id}>
                <strong>{item.name}</strong> — {item.quantity} {item.unit} kaldı (kritik seviye:{' '}
                {item.criticalLevel})
                {item.severity === 'OUT' && ' · TÜKENDİ'}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ---------------- Riskli randevular ---------------- */}
      {risky.length > 0 && (
        <section className="rounded-2xl border border-amber-300 bg-amber-50 p-4">
          <h2 className="font-semibold text-amber-900">Bugün riskli görünen randevular</h2>
          <p className="mt-1 text-xs text-amber-800">
            Skor, telefon numarasının geçmiş gelmeme oranından hesaplanır. Hangi salonlarda ne
            olduğu GÖRÜNMEZ — yalnızca toplulaştırılmış oran.
          </p>
          <ul className="mt-2 space-y-1 text-sm text-amber-900">
            {risky.map((a) => {
              const risk = a.risk!;
              return (
                <li key={a.id}>
                  {minutesToLabel(a.startMin)} · {a.customer.firstName} {a.customer.lastName ?? ''} —{' '}
                  <strong>{risk.label}</strong> ({risk.score}/100) · ön ödeme istenebilir
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* ---------------- Bugünün programı ---------------- */}
      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="section-title">{formatDateTr(todayKey)}</h2>
          <Link href="/admin/takvim" className="text-sm font-medium text-plum-700">
            Takvim görünümü →
          </Link>
        </div>

        {today.length === 0 ? (
          <p className="muted">Bugün için randevu yok.</p>
        ) : (
          <ul className="space-y-2">
            {today.map((a) => {
              const customerAllergies = a.allergies;
              return (
                <li key={a.id} className="card flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="font-medium">
                      <span className="tabular-nums">
                        {minutesToLabel(a.startMin)}–{minutesToLabel(a.endMin)}
                      </span>{' '}
                      · {a.staffName}
                    </p>
                    <p className="muted">
                      <Link
                        href={`/admin/musteriler/${a.customerId}`}
                        className="font-medium text-plum-700 underline"
                      >
                        {a.customer.firstName} {a.customer.lastName ?? ''}
                      </Link>{' '}
                      · {a.services.join(' + ')}
                    </p>
                    {customerAllergies.length > 0 && (
                      <p className="mt-1 text-xs font-semibold text-rose-700">
                        ⚠️ Alerji: {customerAllergies.map((x) => x.label).join(', ')}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {a.shadowParentId && (
                      <span className="badge bg-plum-50 text-plum-700">Ara saat</span>
                    )}
                    {a.isOpportunity && (
                      <span className="badge bg-emerald-50 text-emerald-700">Fırsat</span>
                    )}
                    <span className="badge bg-sand-100 text-ink-700">{a.status}</span>
                    <span className="font-semibold">{formatTl(a.totalPrice)}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: 'danger' | 'warn';
}) {
  const toneClass =
    tone === 'danger'
      ? 'border-rose-300 bg-rose-50'
      : tone === 'warn'
        ? 'border-amber-300 bg-amber-50'
        : 'border-sand-200 bg-white';

  return (
    <div className={`rounded-2xl border p-4 ${toneClass}`}>
      <p className="muted">{label}</p>
      <p className="text-2xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="muted">{sub}</p>}
    </div>
  );
}
