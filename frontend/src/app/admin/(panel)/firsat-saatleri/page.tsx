import { adminApi } from '@/lib/admin-api';
import type { MeResponse } from '@/lib/server-api';
import { minutesToLabel, weekdayNameTr } from '@/lib/time';
import { DiscountSettings, type DiscountSettingsData } from './discount-settings';

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
 * FIRSAT SAATLERİ
 * ====================================================================
 *
 * Üstte: indirim KURALI (seçili günlerde, belirli saatten önce, sabit oran)
 * — fiyatı belirleyen tek şey budur. Altta: doluluk ısı haritası YALNIZCA
 * bilgi amaçlıdır (hangi saatler boş kalıyor); fiyatı etkilemez. Ham doluluk
 * küçük örneklemde yanıltır, bu yüzden Bayes ile daraltılmış değer gösterilir.
 */
export default async function OpportunityPage() {
  // Skorlama FastAPI'de yapılır; bu sayfa yalnızca ızgarayı çizer.
  const me = await adminApi<MeResponse>('/api/me');
  const canManage = (me.staff?.role ?? 'STAFF') !== 'STAFF';
  const [data, discount] = await Promise.all([
    adminApi<OpportunityResponse>('/api/admin/stats/opportunity'),
    canManage
      ? adminApi<DiscountSettingsData>('/api/admin/settings/discount')
      : Promise.resolve(null),
  ]);

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

  const settingsCard = discount ? (
    <DiscountSettings initial={discount} />
  ) : (
    <section className="card !p-4">
      <h2 className="eyebrow">İndirim kuralı</h2>
      <p className="muted mt-1 text-sm">Kuralı yalnızca yönetici ve salon sahibi değiştirebilir.</p>
    </section>
  );

  if (stats.length === 0) {
    return (
      <div className="space-y-3">
        {settingsCard}
        <div className="card !p-4">
          <p className="muted">
            Henüz doluluk istatistiği yok. `npm run db:seed` çalıştırıldığında geçmiş randevulardan
            üretilir.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {settingsCard}
      <h2 className="eyebrow">Doluluk haritası (bilgi)</h2>
      <p className="muted tabular-nums">
        Şube ortalama doluluğu: %{Math.round(globalMean * 100)} · toplam örneklem {totalSamples}
      </p>

      <div className="overflow-x-auto rounded-[4px] border border-sand-200 bg-white p-3">
        <table className="w-full min-w-[560px] border-separate border-spacing-1 text-xs">
          <thead>
            <tr>
              <th className="eyebrow text-left !text-ink-500">Gün</th>
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
                      <td key={slotMin} className="rounded-[2px] bg-sand-100 p-1 text-center text-ink-500">
                        —
                      </td>
                    );
                  }
                  // Yoğunluk arttıkça mor koyulaşır; fırsat saatleri yeşile kaçar.
                  const intensity = cell.adjustedOccupancy;
                  const background = `rgba(110, 43, 58, ${0.08 + intensity * 0.7})`;

                  return (
                    <td
                      key={slotMin}
                      className="rounded-[2px] p-1 text-center tabular-nums"
                      style={{ background, color: intensity > 0.55 ? 'white' : undefined }}
                      title={`Ham doluluk %${Math.round(cell.rawOccupancy * 100)} · düzeltilmiş %${Math.round(
                        cell.adjustedOccupancy * 100,
                      )} · örneklem ${cell.sampleSize}`}
                    >
                      {Math.round(cell.adjustedOccupancy * 100)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>

        <div className="mt-3 flex flex-wrap gap-4 text-xs text-ink-500">
          <span className="flex items-center gap-1">
            <span className="inline-block h-3 w-5 rounded-[2px]" style={{ background: 'rgba(110,43,58,0.75)' }} />
            dolu saat (düzeltilmiş doluluk %)
          </span>
        </div>
      </div>

      <section className="card !p-4">
        <h2 className="eyebrow">En boş 8 saat</h2>
        <p className="muted mt-1 text-xs">
          Yalnızca bilgi: indirim bu listeye göre değil, yukarıdaki kurala göre verilir.
        </p>
        <ul className="mt-2 divide-y divide-sand-100 text-sm">
          {best.map(([key, cell]) => {
            const [weekday, slotMin] = key.split(':').map(Number);
            return (
              <li key={key} className="flex justify-between gap-3 py-1.5">
                <span>
                  {weekdayNameTr(weekday)} {minutesToLabel(slotMin)}
                </span>
                <span className="tabular-nums">
                  doluluk %{Math.round(cell.adjustedOccupancy * 100)}
                </span>
              </li>
            );
          })}
          {best.length === 0 && <li className="muted">Belirgin şekilde boş kalan saat yok.</li>}
        </ul>
      </section>
    </div>
  );
}
