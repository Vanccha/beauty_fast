'use client';

import { Plus, X } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ApiError, apiSend } from '@/lib/api-client';

export interface RecipeItem {
  id: number;
  name: string;
  unit: string;
}

export interface RecipeService {
  id: number;
  name: string;
  isActive: boolean;
  consumables: { itemId: number; itemName: string; unit: string; qtyPerUse: number }[];
}

/** "0,5" -> 0.5; geçersiz ya da <= 0 ise null. */
function parseQty(raw: string): number | null {
  const value = Number(raw.trim().replace(',', '.'));
  return raw.trim() !== '' && Number.isFinite(value) && value > 0 ? value : null;
}

interface Line {
  itemId: number;
  qty: string;
}

function toLines(service: RecipeService): Line[] {
  return service.consumables.map((c) => ({ itemId: c.itemId, qty: String(c.qtyPerUse) }));
}

function ServiceRecipe({ service, items }: { service: RecipeService; items: RecipeItem[] }) {
  const router = useRouter();
  const itemById = new Map(items.map((i) => [i.id, i]));
  const [lines, setLines] = useState<Line[]>(() => toLines(service));
  const [saved, setSaved] = useState<string>(() => JSON.stringify(toLines(service)));
  const [newItem, setNewItem] = useState('');
  const [newQty, setNewQty] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const dirty = JSON.stringify(lines) !== saved;
  const available = items.filter((i) => !lines.some((l) => l.itemId === i.id));

  function touch(next: Line[]) {
    setLines(next);
    setOk(false);
    setError(null);
  }

  function add() {
    const qty = parseQty(newQty);
    if (!newItem) return setError('Eklenecek malzemeyi seçin.');
    if (qty === null) return setError('Miktar 0’dan büyük bir sayı olmalı.');
    touch([...lines, { itemId: Number(newItem), qty: String(qty) }]);
    setNewItem('');
    setNewQty('');
  }

  async function save() {
    const consumables: { itemId: number; qtyPerUse: number }[] = [];
    for (const line of lines) {
      const qty = parseQty(line.qty);
      if (qty === null) {
        setOk(false);
        setError('Tüm miktarlar 0’dan büyük bir sayı olmalı.');
        return;
      }
      consumables.push({ itemId: line.itemId, qtyPerUse: qty });
    }
    setBusy(true);
    setError(null);
    setOk(false);
    try {
      await apiSend<{ service: RecipeService }>(`/api/admin/recipes/${service.id}`, 'PUT', { consumables });
      setSaved(JSON.stringify(lines));
      setOk(true);
      router.refresh();
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setError('Reçete düzenlemek için yönetici yetkisi gerekir.');
      } else {
        setError(e instanceof ApiError ? e.message : 'Reçete kaydedilemedi.');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <article className={`card !p-3 ${service.isActive ? '' : 'opacity-60'}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium text-ink-900">
          {service.name}
          {!service.isActive && (
            <span className="badge ml-2 border border-sand-200 bg-transparent">pasif</span>
          )}
        </p>
        {dirty && <span className="muted text-xs">Kaydedilmemiş değişiklik</span>}
      </div>

      <div className="mt-2 space-y-1.5">
        {lines.length === 0 && <p className="muted">Bu hizmet için malzeme tanımlı değil.</p>}
        {lines.map((line, index) => {
          const item = itemById.get(line.itemId);
          const invalid = parseQty(line.qty) === null;
          return (
            <div key={line.itemId} className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-sm">
                {item?.name ?? service.consumables.find((c) => c.itemId === line.itemId)?.itemName}
              </span>
              <input
                className={`field !w-24 ${invalid ? 'border-rose-300' : ''}`}
                inputMode="decimal"
                aria-label={`${item?.name ?? 'Malzeme'} miktarı`}
                value={line.qty}
                onChange={(e) =>
                  touch(lines.map((l, i) => (i === index ? { ...l, qty: e.target.value } : l)))
                }
              />
              <span className="muted w-10 shrink-0 text-xs">{item?.unit}</span>
              <button
                type="button"
                className="btn-ghost btn-sm"
                aria-label={`${item?.name ?? 'Malzeme'} çıkar`}
                onClick={() => touch(lines.filter((_, i) => i !== index))}
              >
                <X size={16} strokeWidth={1.5} aria-hidden />
              </button>
            </div>
          );
        })}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-sand-200 pt-3">
        <select
          className="field !w-auto min-w-0 flex-1"
          value={newItem}
          onChange={(e) => setNewItem(e.target.value)}
          aria-label="Malzeme ekle"
          disabled={available.length === 0}
        >
          <option value="">{available.length === 0 ? 'Eklenecek malzeme kalmadı' : 'Malzeme seç…'}</option>
          {available.map((i) => (
            <option key={i.id} value={i.id}>
              {i.name} ({i.unit})
            </option>
          ))}
        </select>
        <input
          className="field !w-24"
          inputMode="decimal"
          placeholder="Miktar"
          aria-label="Yeni malzeme miktarı"
          value={newQty}
          onChange={(e) => setNewQty(e.target.value)}
        />
        <button type="button" className="btn-secondary btn-sm" onClick={add}>
          <Plus size={14} strokeWidth={1.5} aria-hidden />
          Malzeme ekle
        </button>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button type="button" className="btn-primary btn-sm" disabled={busy || !dirty} onClick={save}>
          {busy ? 'Kaydediliyor…' : 'Kaydet'}
        </button>
        {ok && !dirty && <span className="text-sm text-ink-700">Reçete kaydedildi.</span>}
        {error && <span className="text-sm text-danger-700">{error}</span>}
      </div>
    </article>
  );
}

export function RecipeEditor({ services, items }: { services: RecipeService[]; items: RecipeItem[] }) {
  if (services.length === 0) return <p className="muted">Henüz hizmet yok.</p>;
  const sorted = [...services].sort((a, b) => Number(b.isActive) - Number(a.isActive));
  return (
    <div className="space-y-1.5">
      {sorted.map((s) => (
        <ServiceRecipe key={s.id} service={s} items={items} />
      ))}
    </div>
  );
}

