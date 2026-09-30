import Link from 'next/link';

import { formatTl } from '@/lib/api-client';
import { adminApi } from '@/lib/admin-api';

export const dynamic = 'force-dynamic';

interface CustomerSummary {
  id: number;
  firstName: string;
  lastName: string | null;
  phone: string;
  tier: string;
  loyaltyPoints: number;
  totalSpend: number;
  visitCount: number;
  noShowCount: number;
  lastVisitDaysAgo: number | null;
  localRiskScore: number;
  segment: {
    segment: string;
    badge: string;
    tone: string;
    showRate: number;
    warning: string | null;
  };
}

const SEGMENTS = ['hepsi', 'VIP', 'SADIK', 'RISKLI', 'UYUYAN', 'YENI', 'STANDART'] as const;

const TONE_CLASS: Record<string, string> = {
  violet: 'bg-violet-50 text-violet-700',
  emerald: 'bg-emerald-50 text-emerald-700',
  red: 'bg-rose-50 text-rose-700',
  amber: 'bg-amber-50 text-amber-800',
  sky: 'bg-sky-50 text-sky-700',
  slate: 'bg-sand-100 text-ink-700',
};

/**
 * Müşteri listesi + segment rozetleri.
 *
 * Segment `segmentCustomer` ile hesaplanır (VIP / SADIK / RISKLI /
 * UYUYAN / YENI / STANDART). Buradaki risk göstergesi SALON İÇİ gelmeme
 * oranıdır; çapraz-salon skoru yalnızca müşteri kartında sorgulanır.
 */
export default async function CustomersPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; segment?: string }>;
}) {
  const { q, segment } = await searchParams;

  // Arama, segment filtresi ve sıralama (harcama, sonra ziyaret) FastAPI'de yapılır.
  const query = new URLSearchParams();
  if (q) query.set('q', q);
  if (segment) query.set('segment', segment);
  const qs = query.toString();
  const { customers: rows } = await adminApi<{ customers: CustomerSummary[] }>(
    `/api/admin/customers${qs ? `?${qs}` : ''}`,
  );

  return (
    <div className="space-y-4">
      <h1 className="section-title">Müşteriler ({rows.length})</h1>

      <form className="flex gap-2" action="/admin/musteriler">
        <input
          name="q"
          defaultValue={q ?? ''}
          className="field"
          placeholder="Ad veya telefon ara"
          aria-label="Müşteri ara"
        />
        {segment && <input type="hidden" name="segment" value={segment} />}
        <button className="btn-primary">Ara</button>
      </form>

      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
        {SEGMENTS.map((s) => (
          <Link
            key={s}
            href={`/admin/musteriler?segment=${s}${q ? `&q=${encodeURIComponent(q)}` : ''}`}
            className={`btn shrink-0 ${
              (segment ?? 'hepsi') === s
                ? 'bg-plum-600 text-white'
                : 'border border-sand-300 bg-white'
            }`}
          >
            {s === 'hepsi' ? 'Hepsi' : s}
          </Link>
        ))}
      </div>

      <ul className="space-y-2">
        {rows.map((c) => (
          <li key={c.id}>
            <Link
              href={`/admin/musteriler/${c.id}`}
              className="card flex flex-wrap items-center justify-between gap-3 hover:border-plum-300"
            >
              <div className="min-w-0">
                <p className="font-medium">
                  {c.firstName} {c.lastName ?? ''}
                </p>
                <p className="muted">
                  0{c.phone} · {c.visitCount} ziyaret
                  {c.lastVisitDaysAgo !== null && ` · son ${c.lastVisitDaysAgo} gün önce`}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <span className={`badge ${TONE_CLASS[c.segment.tone] ?? TONE_CLASS.slate}`}>
                  {c.segment.badge}
                </span>
                <span className="badge bg-sand-100 text-ink-700">{c.tier}</span>
                {c.noShowCount > 0 && (
                  <span className="badge bg-rose-50 text-rose-700">
                    {c.noShowCount} gelmedi
                  </span>
                )}
                <span className="font-semibold">{formatTl(c.totalSpend)}</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>

      {rows.length === 0 && <p className="muted">Eşleşen müşteri yok.</p>}
    </div>
  );
}
