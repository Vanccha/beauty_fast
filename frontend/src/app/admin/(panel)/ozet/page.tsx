import { AlertTriangle, ArrowRight, ShieldAlert } from 'lucide-react';
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
 * GENEL BAKIŞ — günün özeti
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
export default async function AdminOverview() {
  // Veri FastAPI backend'inden gelir; bu sayfa veritabanını bilmez.
  const data = await serverApi<DashboardResponse>('/api/admin/dashboard');

  const todayKey = data.date;
  const today = data.appointments;
  const critical = data.criticalStock;
  const pendingNotifications = data.pendingNotifications;

  // Risk eşiği 45: bu skorun üstü "ön ödeme istenebilir" demektir.
  const risky = today.filter((a) => (a.risk?.score ?? 0) >= 45);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        <Stat label="Bugünkü randevu" value={String(today.length)} />
        <Stat
          label="Tamamlanan (7 gün)"
          value={String(data.week.completed)}
          sub={formatTl(data.week.revenue)}
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
        <section className="alert alert-danger flex-col !items-stretch !gap-2">
          <div className="flex items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <AlertTriangle size={16} strokeWidth={1.5} aria-hidden />
              Kritik stok uyarısı
            </h2>
            <Link href="/admin/stok" className="btn-link">
              Stoğa git
            </Link>
          </div>
          <ul className="space-y-1 text-sm">
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
        <section className="alert alert-warning flex-col !items-stretch !gap-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <ShieldAlert size={16} strokeWidth={1.5} aria-hidden />
            Bugün riskli görünen randevular
          </h2>
          <p className="text-xs">
            Skor, telefon numarasının geçmiş gelmeme oranından hesaplanır. Hangi salonlarda ne
            olduğu GÖRÜNMEZ — yalnızca toplulaştırılmış oran.
          </p>
          <ul className="space-y-1 text-sm">
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
        <div className="flex items-center justify-between gap-3">
          <h2 className="section-title">{formatDateTr(todayKey)}</h2>
          <Link href="/admin/takvim" className="btn-link">
            Takvim görünümü
            <ArrowRight size={14} strokeWidth={1.5} aria-hidden />
          </Link>
        </div>

        {today.length === 0 ? (
          <p className="muted">Bugün için randevu yok.</p>
        ) : (
          <ul className="space-y-2">
            {today.map((a) => (
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
                      className="font-medium text-plum-700 underline underline-offset-2"
                    >
                      {a.customer.firstName} {a.customer.lastName ?? ''}
                    </Link>{' '}
                    · {a.services.join(' + ')}
                  </p>
                  {a.allergies.length > 0 && (
                    <p className="mt-1 flex items-center gap-1 text-xs font-semibold text-danger-700">
                      <AlertTriangle size={12} strokeWidth={1.5} aria-hidden />
                      Alerji: {a.allergies.map((x) => x.label).join(', ')}
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {a.shadowParentId && <span className="badge bg-plum-50 text-plum-700">Ara saat</span>}
                  {a.isOpportunity && (
                    <span className="badge bg-success-50 text-success-700">Fırsat</span>
                  )}
                  <span className="badge">{a.status}</span>
                  <span className="font-semibold tabular-nums">{formatTl(a.totalPrice)}</span>
                </div>
              </li>
            ))}
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
      ? 'border-danger-600/30 bg-danger-50'
      : tone === 'warn'
        ? 'border-warning-600/30 bg-warning-50'
        : 'border-sand-200 bg-white';

  return (
    <div className={`rounded-[4px] border px-3 py-2.5 ${toneClass}`}>
      <p className="eyebrow !tracking-[0.12em]">{label}</p>
      <p className="display text-2xl tabular-nums">{value}</p>
      {sub && <p className="muted !text-xs">{sub}</p>}
    </div>
  );
}
