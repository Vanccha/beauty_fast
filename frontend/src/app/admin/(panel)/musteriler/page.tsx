import { Search } from 'lucide-react';
import Link from 'next/link';

import { formatTl } from '@/lib/api-client';
import { adminApi } from '@/lib/admin-api';
import { formatPhone } from '@/lib/phone';

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
  violet: 'border border-plum-300 bg-transparent text-plum-700',
  emerald: 'border border-emerald-300 bg-transparent text-emerald-700',
  red: 'border border-rose-300 bg-transparent text-rose-700',
  amber: 'border border-brass-300 bg-transparent text-brass-700',
  sky: 'border border-sand-300 bg-transparent text-ink-700',
  slate: 'border border-sand-200 bg-sand-100 text-ink-700',
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
    <div className="space-y-3">
      <form className="flex gap-2" action="/admin/musteriler">
        <input
          name="q"
          defaultValue={q ?? ''}
          className="field !min-h-10"
          placeholder="Ad veya telefon ara"
          aria-label="Müşteri ara"
        />
        {segment && <input type="hidden" name="segment" value={segment} />}
        <button className="btn-primary btn-sm">
          <Search size={14} strokeWidth={1.5} aria-hidden /> Ara
        </button>
      </form>

      <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
        <span className="eyebrow mr-1 shrink-0 tabular-nums">{rows.length} kişi</span>
        {SEGMENTS.map((s) => (
          <Link
            key={s}
            href={`/admin/musteriler?segment=${s}${q ? `&q=${encodeURIComponent(q)}` : ''}`}
            className={`chip !min-h-8 shrink-0 !px-3 text-xs ${
              (segment ?? 'hepsi') === s ? 'chip-active chip-primary' : ''
            }`}
          >
            {s === 'hepsi' ? 'Hepsi' : s}
          </Link>
        ))}
      </div>

      <ul className="space-y-1.5">
        {rows.map((c) => (
          <li key={c.id}>
            <Link
              href={`/admin/musteriler/${c.id}`}
              className="card flex flex-wrap items-center justify-between gap-x-3 gap-y-2 !p-3 hover:border-ink-900"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-ink-900">
                  {c.firstName} {c.lastName ?? ''}
                </p>
                <p className="muted text-xs tabular-nums">
                  {formatPhone(c.phone)} · {c.visitCount} ziyaret
                  {c.lastVisitDaysAgo !== null && ` · son ${c.lastVisitDaysAgo} gün önce`}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <span className={`badge ${TONE_CLASS[c.segment.tone] ?? TONE_CLASS.slate}`}>
                  {c.segment.badge}
                </span>
                <span className="badge border border-sand-200 bg-sand-100 text-ink-700">{c.tier}</span>
                {c.noShowCount > 0 && (
                  <span className="badge border border-rose-300 bg-transparent text-rose-700">
                    {c.noShowCount} gelmedi
                  </span>
                )}
                <span className="text-sm font-semibold tabular-nums">{formatTl(c.totalSpend)}</span>
              </div>
            </Link>
          </li>
        ))}
      </ul>

      {rows.length === 0 && <p className="muted">Eşleşen müşteri yok.</p>}
    </div>
  );
}
