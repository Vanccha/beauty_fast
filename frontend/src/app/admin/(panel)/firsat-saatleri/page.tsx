import { adminApi } from '@/lib/admin-api';
import { minutesToLabel, weekdayNameTr } from '@/lib/time';

export const dynamic = 'force-dynamic';

interface OpportunityCell {
  weekday: number;
  weekdayLabel: string;
  slotMin: number;
  slotLabel: string;
  sampleSize: number;
  rawOccupancy: number;
  adjustedOccupancy: number;
  opportunityIndex: number;
  discountRate: number;
  isOpportunity: boolean;
  label: string;
}

interface OpportunityResponse {
  globalMeanOccupancy: number;
  totalSamples: number;
  slotMinutes: number[];
  cells: OpportunityCell[];
  bestOpportunities: OpportunityCell[];
}

/**
 * ====================================================================
 * FIRSAT SAATİ ISI HARİTASI
 * ====================================================================
 *
 * Ham doluluk oranı GÖSTERİLMEZ — küçük örneklemde yanıltır ("salı 10:00
 * %0 dolu" aslında "salı 10:00'ı 3 kez ölçtük" demek olabilir).
 *
 * `score_opportunity` (FastAPI) Bayes shrinkage uygular: gözlem az ise
 * oran şube ortalamasına çekilir. İndirim yalnızca daraltılmış doluluk
 * eşiğin altına düştüğünde açılır ve %5'lik adımlara yuvarlanır.
 */
export default async function OpportunityPage() {
  // Skorlama FastAPI'de yapılır; bu sayfa yalnızca ızgarayı çizer.
  const data = await adminApi<OpportunityResponse>('/api/admin/stats/opportunity');

  const stats = data.cells;
  const totalSamples = data.totalSamples;
  const globalMean = data.globalMeanOccupancy;

  const slots = data.slotMinutes;
  const weekdays = [1, 2, 3, 4, 5, 6, 0]; // Pazartesi başlangıçlı hafta

  const scored = new Map<string, OpportunityCell>();
  for (const cell of stats) scored.set(`${cell.weekday}:${cell.slotMin}`, cell);

  const best = data.bestOpportunities.map(
    (cell) => [`${cell.weekday}:${cell.slotMin}`, cell] as const,
  );

  if (stats.length === 0) {
    return (
      <div className="card">
        <h1 className="section-title">Fırsat saatleri</h1>
        <p className="mt-2 muted">
          Henüz doluluk istatistiği yok. `npm run db:seed` çalıştırıldığında geçmiş randevulardan
          üretilir.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="section-title">Fırsat saatleri</h1>
        <p className="muted">
          Şube ortalama doluluğu: %{Math.round(globalMean * 100)} · toplam örneklem {totalSamples}
        </p>
      </div>

      <div className="overflow-x-auto rounded-2xl border border-sand-200 bg-white p-3">
        <table className="w-full min-w-[560px] border-separate border-spacing-1 text-xs">
          <thead>
            <tr>
              <th className="text-left font-medium text-ink-500">Gün</th>
              {slots.map((s) => (
                <th key={s} className="font-medium tabular-nums text-ink-500">
                  {minutesToLabel(s)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {weekdays.map((weekday) => (
              <tr key={weekday}>
                <th className="whitespace-nowrap pr-2 text-left font-medium">
                  {weekdayNameTr(weekday)}
                </th>
                {slots.map((slotMin) => {
                  const cell = scored.get(`${weekday}:${slotMin}`);
                  if (!cell) {
                    return (
                      <td key={slotMin} className="rounded bg-sand-100 p-1 text-center text-ink-500">
                        —
                      </td>
                    );
                  }
                  // Yoğunluk arttıkça mor koyulaşır; fırsat saatleri yeşile kaçar.
                  const intensity = cell.adjustedOccupancy;
                  const background = cell.isOpportunity
                    ? `rgba(16, 185, 129, ${0.15 + cell.opportunityIndex * 0.6})`
                    : `rgba(141, 91, 127, ${0.1 + intensity * 0.7})`;

                  return (
                    <td
                      key={slotMin}
                      className="rounded p-1 text-center tabular-nums"
                      style={{ background, color: intensity > 0.55 ? 'white' : undefined }}
                      title={`Ham doluluk %${Math.round(cell.rawOccupancy * 100)} · düzeltilmiş %${Math.round(
                        cell.adjustedOccupancy * 100,
                      )} · örneklem ${cell.sampleSize}`}
                    >
                      {cell.discountRate > 0
                        ? `%${Math.round(cell.discountRate * 100)}`
                        : `${Math.round(cell.adjustedOccupancy * 100)}`}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>

        <div className="mt-3 flex flex-wrap gap-4 text-xs text-ink-500">
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-5 rounded" style={{ background: 'rgba(141,91,127,0.75)' }} />
            dolu saat (düzeltilmiş doluluk %)
          </span>
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-5 rounded" style={{ background: 'rgba(16,185,129,0.6)' }} />
            fırsat saati (önerilen indirim %)
          </span>
        </div>
      </div>

      <section className="card">
        <h2 className="section-title">En verimsiz 8 saat</h2>
        <p className="muted">
          Bu saatlerde açılan randevulara otomatik indirim uygulanır ve sadakat puanı çarpanı
          yükselir — ölü saati doldurmak teşvik edilir.
        </p>
        <ul className="mt-2 space-y-1 text-sm">
          {best.map(([key, cell]) => {
            const [weekday, slotMin] = key.split(':').map(Number);
            return (
              <li key={key} className="flex justify-between">
                <span>
                  {weekdayNameTr(weekday)} {minutesToLabel(slotMin)}
                </span>
                <span className="tabular-nums">
                  %{Math.round(cell.discountRate * 100)} indirim ·{' '}
                  {cell.label}
                </span>
              </li>
            );
          })}
          {best.length === 0 && <li className="muted">Şu an fırsat eşiğini geçen saat yok.</li>}
        </ul>
      </section>
    </div>
  );
}
