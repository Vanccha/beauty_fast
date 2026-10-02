'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ApiError, apiSend } from '@/lib/api-client';

interface StockItem {
  id: number;
  name: string;
  unit: string;
  quantity: number;
  criticalLevel: number;
  isCritical: boolean;
  usedBy: string[];
  recentMovements: { id: number; delta: number; reason: string; createdAt: string }[];
}

/**
 * Tek bir stok kalemi. Giriş/fire hareketleri `PATCH /api/admin/inventory`
 * ile yazılır; miktar ve hareket kaydı aynı transaction'da değişir.
 */
export function StockRow({ item }: { item: StockItem }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState<'PURCHASE' | 'MANUAL_ADJUST' | 'WASTE'>('PURCHASE');
  const [critical, setCritical] = useState(String(item.criticalLevel));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const value = Number(amount);
      await apiSend('/api/admin/inventory', 'PATCH', {
        itemId: item.id,
        // Fire ve düzeltme negatif, tedarik pozitif yazılır.
        delta: Number.isFinite(value) && value !== 0 ? (reason === 'PURCHASE' ? value : -Math.abs(value)) : undefined,
        reason,
        criticalLevel: Number(critical) !== item.criticalLevel ? Number(critical) : undefined,
      });
      setAmount('');
      setOpen(false);
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Güncellenemedi.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={`card !p-3 ${item.isCritical ? 'border-rose-300' : ''}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink-900">
            {item.name}
            {item.isCritical && (
              <span className="badge ml-2 border border-rose-300 bg-transparent text-rose-700">kritik</span>
            )}
          </p>
          <p className="muted">
            {item.usedBy.length > 0 ? `Kullanan: ${item.usedBy.join(', ')}` : 'Reçeteye bağlı değil'}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-right">
            <p className="text-base font-semibold tabular-nums">
              {item.quantity} <span className="text-sm font-normal">{item.unit}</span>
            </p>
            <p className="muted text-xs">kritik: {item.criticalLevel}</p>
          </div>
          <button type="button" className="btn-secondary btn-sm" onClick={() => setOpen((v) => !v)}>
            {open ? 'Kapat' : 'Düzenle'}
          </button>
        </div>
      </div>

      {open && (
        <form onSubmit={submit} className="mt-3 border-t border-sand-200 pt-3 grid grid-cols-1 gap-2 md:grid-cols-4">
          <input
            className="field"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder={`Miktar (${item.unit})`}
          />
          <select
            className="field"
            value={reason}
            onChange={(e) => setReason(e.target.value as typeof reason)}
          >
            <option value="PURCHASE">Tedarik (giriş)</option>
            <option value="WASTE">Fire (düşüm)</option>
            <option value="MANUAL_ADJUST">Sayım düzeltmesi (düşüm)</option>
          </select>
          <input
            className="field"
            inputMode="decimal"
            value={critical}
            onChange={(e) => setCritical(e.target.value)}
            placeholder="Kritik seviye"
          />
          <button className="btn-primary btn-sm" disabled={busy}>
            {busy ? 'Kaydediliyor…' : 'Kaydet'}
          </button>

          {error && <p className="text-sm text-danger-700 md:col-span-4">{error}</p>}

          {item.recentMovements.length > 0 && (
            <ul className="muted md:col-span-4">
              {item.recentMovements.map((m) => (
                <li key={m.id}>
                  {new Date(m.createdAt).toLocaleDateString('tr-TR')} ·{' '}
                  {m.delta > 0 ? `+${m.delta}` : m.delta} · {m.reason}
                </li>
              ))}
            </ul>
          )}
        </form>
      )}
    </article>
  );
}
