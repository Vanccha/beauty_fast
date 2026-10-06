import { redirect } from 'next/navigation';
import Link from 'next/link';

import { adminApi } from '@/lib/admin-api';
import { ApiError, formatTl } from '@/lib/api-client';

export const dynamic = 'force-dynamic';

interface Totals {
  count: number;
  revenue: number;
  commission: number;
}

interface Report {
  year: number;
  month: number | null;
  availableYears: number[];
  summary: Totals & {
    net: number;
    average: number;
    cancelled: number;
    noShow: number;
    previous: Totals & { year: number; month: number | null };
    changePercent: number | null;
  };
  months: (Totals & { month: number; net: number })[];
  days: { date: string; count: number; revenue: number }[];
  byStaff: { staffId: number; name: string; count: number; revenue: number; commissionPercent: number; commission: number }[];
  byService: { serviceId: number; name: string; count: number; revenue: number }[];
}

const MONTHS = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];

function href(year: number, month: number | null): string {
  return `/admin/gelir?year=${year}${month ? `&month=${month}` : ''}`;
}

/**
 * Stüdyo gelir raporu — YALNIZCA salon sahibi (API de `OWNER` ister).
 * Gelir = tamamlanan randevu cirosu. Personel payı güncel kazanç yüzdeleriyle
 * hesaplanır; net = gelir − personel payı.
 */
export default async function RevenuePage({
  searchParams,
}: {
  searchParams: Promise<{ year?: string; month?: string }>;
}) {
  const params = await searchParams;
  const year = Number(params.year);
  const month = Number(params.month);
  const query = new URLSearchParams();
  if (!params.year && !params.month) {
    // İlk giriş: içinde bulunulan ay (İstanbul saatiyle). Yıllık görünüm "Yıllık" düğmesiyle açılır.
    const [y, m] = new Intl.DateTimeFormat('en-CA', { timeZone: 'Europe/Istanbul' }).format(new Date()).split('-');
    query.set('year', y);
    query.set('month', String(Number(m)));
  } else {
    if (Number.isInteger(year) && year >= 2000) query.set('year', String(year));
    if (Number.isInteger(month) && month >= 1 && month <= 12) query.set('month', String(month));
  }

  let data: Report;
  try {
    data = await adminApi<Report>(`/api/admin/reports/revenue${query.toString() ? `?${query}` : ''}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) redirect('/admin');
    throw e;
  }

  const { summary } = data;
  const periodLabel = data.month ? `${MONTHS[data.month - 1]} ${data.year}` : `${data.year} yılı`;
  const prevLabel = summary.previous.month
    ? `${MONTHS[summary.previous.month - 1]} ${summary.previous.year}`
    : `${summary.previous.year}`;

  const bars = data.month
    ? data.days.map((d) => ({ key: d.date, label: String(Number(d.date.slice(8))), value: d.revenue, href: null as string | null }))
    : data.months.map((m) => ({ key: String(m.month), label: MONTHS[m.month - 1].slice(0, 3), value: m.revenue, href: href(data.year, m.month) }));
  const max = Math.max(1, ...bars.map((b) => b.value));

  return (
    <div className="space-y-4">
      {/* Dönem seçimi */}
      <div className="card space-y-3 !p-3">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="label !mb-0 mr-1">Yıl</span>
          {data.availableYears.map((y) => (
            <Link key={y} href={href(y, null)} className={`chip ${y === data.year ? 'chip-active' : ''}`} aria-pressed={y === data.year}>
              {y}
            </Link>
          ))}
        </div>
        <div className="flex flex-wrap gap-1.5">
          <Link href={href(data.year, null)} className={`chip ${data.month === null ? 'chip-active' : ''}`} aria-pressed={data.month === null}>
            Yıllık
          </Link>
          {MONTHS.map((name, i) => (
            <Link
              key={name}
              href={href(data.year, i + 1)}
              className={`chip ${data.month === i + 1 ? 'chip-active' : ''}`}
              aria-pressed={data.month === i + 1}
            >
              {name}
            </Link>
          ))}
        </div>
      </div>

      <h2 className="display text-2xl text-plum-700">{periodLabel}</h2>

      {/* Özet */}
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4 md:gap-3">
        <Stat label="Toplam gelir" value={formatTl(summary.revenue)} strong>
          {summary.changePercent === null ? (
            <span className="muted text-xs">{prevLabel} verisi yok</span>
          ) : (
            <span className={`text-xs font-semibold ${summary.changePercent >= 0 ? 'text-success-700' : 'text-danger-700'}`}>
              {summary.changePercent >= 0 ? '▲' : '▼'} %{Math.abs(summary.changePercent)}{' '}
              <span className="font-normal text-ink-500">({prevLabel}: {formatTl(summary.previous.revenue)})</span>
            </span>
          )}
        </Stat>
        <Stat label="Tamamlanan randevu" value={String(summary.count)}>
          <span className="muted text-xs">
            {summary.cancelled} iptal · {summary.noShow} gelmedi
          </span>
        </Stat>
        <Stat label="Ortalama sepet" value={formatTl(summary.average)} />
        <Stat label="Personel payı" value={formatTl(summary.commission)}>
          <span className="muted text-xs">Stüdyo net: {formatTl(summary.net)}</span>
        </Stat>
      </div>

      {/* Grafik */}
      <section className="card !p-3 md:!p-4" aria-label={data.month ? 'Günlük gelir' : 'Aylık gelir'}>
        <h3 className="eyebrow mb-3">{data.month ? 'Günlük gelir' : 'Aylık gelir'}</h3>
        <div className="flex h-44 items-end gap-1 md:gap-1.5" role="list">
          {bars.map((b) => {
            const bar = (
              <>
                <span className="mb-1 hidden text-[10px] tabular-nums text-ink-500 md:block">
                  {b.value > 0 ? Math.round(b.value / 1000 * 10) / 10 + 'b' : ''}
                </span>
                <span
                  className={`w-full rounded-t-md ${b.value > 0 ? 'bg-plum-600' : 'bg-sand-200'}`}
                  style={{ height: `${Math.max(2, (b.value / max) * 100)}%` }}
                  title={`${b.label}: ${formatTl(b.value)}`}
                />
              </>
            );
            return (
              <div key={b.key} role="listitem" className="flex h-full min-w-0 flex-1 flex-col items-center justify-end">
                {b.href ? (
                  <Link href={b.href} className="flex h-full w-full flex-col items-center justify-end no-underline hover:opacity-80">
                    {bar}
                  </Link>
                ) : (
                  <div className="flex h-full w-full flex-col items-center justify-end">{bar}</div>
                )}
                <span className="mt-1 text-[10px] text-ink-500 md:text-xs">{b.label}</span>
              </div>
            );
          })}
        </div>
        {!data.month && <p className="muted mt-2 text-xs">Bir aya tıklayınca günlük döküm açılır. Değerler bin TL (b).</p>}
      </section>

      {/* Geçmiş aylar tablosu (yıllık görünüm) */}
      {!data.month && (
        <section className="card !p-3 md:!p-4">
          <h3 className="eyebrow mb-2">Aylara göre</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-sm tabular-nums">
              <thead>
                <tr className="text-left text-xs text-ink-500">
                  <th className="py-1.5 font-medium">Ay</th>
                  <th className="py-1.5 text-right font-medium">Randevu</th>
                  <th className="py-1.5 text-right font-medium">Gelir</th>
                  <th className="py-1.5 text-right font-medium">Personel payı</th>
                  <th className="py-1.5 text-right font-medium">Net</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-sand-200">
                {data.months.map((m) => (
                  <tr key={m.month} className={m.revenue === 0 ? 'text-ink-400' : ''}>
                    <td className="py-1.5">
                      <Link href={href(data.year, m.month)} className="text-plum-700 hover:underline">
                        {MONTHS[m.month - 1]}
                      </Link>
                    </td>
                    <td className="py-1.5 text-right">{m.count}</td>
                    <td className="py-1.5 text-right">{formatTl(m.revenue)}</td>
                    <td className="py-1.5 text-right">{formatTl(m.commission)}</td>
                    <td className="py-1.5 text-right font-semibold">{formatTl(m.net)}</td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-sand-300 font-semibold">
                  <td className="py-1.5">Toplam</td>
                  <td className="py-1.5 text-right">{summary.count}</td>
                  <td className="py-1.5 text-right">{formatTl(summary.revenue)}</td>
                  <td className="py-1.5 text-right">{formatTl(summary.commission)}</td>
                  <td className="py-1.5 text-right">{formatTl(summary.net)}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </section>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        <section className="card !p-3 md:!p-4">
          <h3 className="eyebrow mb-2">Personele göre</h3>
          {data.byStaff.length === 0 ? (
            <p className="muted text-sm">Bu dönemde tamamlanan randevu yok.</p>
          ) : (
            <ul className="divide-y divide-sand-200 text-sm">
              {data.byStaff.map((s) => (
                <li key={s.staffId} className="flex items-center justify-between gap-2 py-1.5">
                  <span className="min-w-0 truncate">
                    {s.name} <span className="muted text-xs">· {s.count} randevu · %{s.commissionPercent}</span>
                  </span>
                  <span className="tabular-nums">
                    {formatTl(s.revenue)} <span className="text-plum-700">→ {formatTl(s.commission)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="card !p-3 md:!p-4">
          <h3 className="eyebrow mb-2">Hizmete göre</h3>
          {data.byService.length === 0 ? (
            <p className="muted text-sm">Bu dönemde tamamlanan randevu yok.</p>
          ) : (
            <ul className="divide-y divide-sand-200 text-sm">
              {data.byService.map((s) => (
                <li key={s.serviceId} className="flex items-center justify-between gap-2 py-1.5">
                  <span className="min-w-0 truncate">
                    {s.name} <span className="muted text-xs">· {s.count} adet</span>
                  </span>
                  <span className="tabular-nums">{formatTl(s.revenue)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      <p className="muted text-xs">
        Gelir, “Tamamlandı” işaretlenen randevuların tutarıdır (indirimler düşülmüş). Kapora ayrı bir gelir sayılmaz.
        Personel payı, personellerin şu anki kazanç yüzdeleriyle hesaplanır.
      </p>
    </div>
  );
}

function Stat({
  label,
  value,
  strong,
  children,
}: {
  label: string;
  value: string;
  strong?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="card !p-3">
      <p className="muted text-xs">{label}</p>
      <p className={`display mt-1 text-xl tabular-nums md:text-2xl ${strong ? 'text-plum-700' : ''}`}>{value}</p>
      {children && <div className="mt-1">{children}</div>}
    </div>
  );
}
