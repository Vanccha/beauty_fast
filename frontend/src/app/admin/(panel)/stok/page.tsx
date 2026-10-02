import { AlertTriangle } from 'lucide-react';

import { adminApi } from '@/lib/admin-api';
import { formatTl } from '@/lib/api-client';
import { StockRow } from './stock-row';

export const dynamic = 'force-dynamic';

interface InventoryResponse {
  items: {
    id: number;
    name: string;
    unit: string;
    quantity: number;
    criticalLevel: number;
    costPerUnit: number | null;
    isCritical: boolean;
    usedByServices: { serviceId: number; name: string | null; qtyPerUse: number }[];
    recentMovements: { id: number; delta: number; reason: string; createdAt: string }[];
  }[];
  criticalWarnings: {
    id: number;
    name: string;
    quantity: number;
    unit: string;
    criticalLevel: number;
    severity: 'OUT' | 'LOW';
  }[];
}

/**
 * Stok yönetimi.
 *
 * Stok, randevu "Tamamlandı" işaretlendiğinde `consumeForAppointment` ile
 * OTOMATİK düşer; buradaki giriş/düzeltme alanları elle tedarik ve fire
 * içindir. `StockMovement` üzerindeki `@@unique([appointmentId, itemId])`
 * sayesinde aynı randevu iki kez tamamlansa bile stok bir kez düşer.
 */
export default async function StockPage() {
  const data = await adminApi<InventoryResponse>('/api/admin/inventory');
  const items = data.items;
  const critical = data.criticalWarnings;

  const totalValue = items.reduce((sum, i) => sum + i.quantity * (i.costPerUnit ?? 0), 0);

  return (
    <div className="space-y-3">
      <p className="muted tabular-nums">Tahmini stok değeri: {formatTl(totalValue)}</p>

      {critical.length > 0 && (
        <div className="rounded-[4px] border border-rose-300 px-3 py-2.5">
          <h2 className="eyebrow flex items-center gap-1.5 !text-rose-700">
            <AlertTriangle size={14} strokeWidth={1.5} aria-hidden />
            {critical.length} kalem kritik seviyede
          </h2>
          <p className="mt-1 text-sm text-ink-700">
            {critical.map((c) => `${c.name} (${c.quantity} ${c.unit})`).join(' · ')}
          </p>
        </div>
      )}

      <div className="space-y-1.5">
        {items.map((item) => (
          <StockRow
            key={item.id}
            item={{
              id: item.id,
              name: item.name,
              unit: item.unit,
              quantity: item.quantity,
              criticalLevel: item.criticalLevel,
              isCritical: item.isCritical,
              usedBy: item.usedByServices.map((u) => `${u.name} (${u.qtyPerUse} ${item.unit})`),
              // Sayfa kalem başına son 3 hareketi gösterir.
              recentMovements: item.recentMovements.slice(0, 3),
            }}
          />
        ))}
      </div>
    </div>
  );
}
