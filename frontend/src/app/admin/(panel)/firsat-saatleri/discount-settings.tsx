'use client';

import { Pencil } from 'lucide-react';
import { useState } from 'react';

import { ApiError, apiSend } from '@/lib/api-client';
import { minutesToLabel } from '@/lib/time';

export interface DiscountSettingsData {
  enabled: boolean;
  rate: number;
  cutoffMin: number;
  cutoffLabel: string;
  /** 0 = Pazar ... 6 = Cumartesi */
  days: number[];
  dayNames: string[];
  cutoffChoices: number[];
  minRate: number;
  maxRate: number;
  summary: string;
}

const RATES = [0.05, 0.1, 0.15, 0.2, 0.25, 0.3];
// Pazartesi başlangıçlı gösterim
const DAY_ORDER = [1, 2, 3, 4, 5, 6, 0];

/**
 * Fırsat saati indirimi: seçilen günlerde (varsayılan hafta içi) belirlenen
 * saatten ÖNCE başlayan randevulara SABİT oran. Kural backend'de tek yerde
 * (`core/opportunity.py: fixed_window_discount`); slot listesi, randevu onayı
 * ve grup randevusu aynı fonksiyonu kullanır.
 */
export function DiscountSettings({ initial }: { initial: DiscountSettingsData }) {
  const [data, setData] = useState(initial);
  const [enabled, setEnabled] = useState(initial.enabled);
  const [rate, setRate] = useState(initial.rate);
  const [cutoff, setCutoff] = useState(initial.cutoffMin);
  const [days, setDays] = useState<number[]>(initial.days);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const dirty =
    enabled !== data.enabled ||
    Math.abs(rate - data.rate) > 1e-9 ||
    cutoff !== data.cutoffMin ||
    [...days].sort().join() !== [...data.days].sort().join();

  function reset(from: DiscountSettingsData) {
    setEnabled(from.enabled);
    setRate(from.rate);
    setCutoff(from.cutoffMin);
    setDays(from.days);
  }

  function toggleDay(d: number) {
    setDays((cur) => (cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d]));
  }

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const next = await apiSend<DiscountSettingsData>('/api/admin/settings/discount', 'PUT', {
        enabled,
        rate,
        cutoffMin: cutoff,
        days,
      });
      setData(next);
      reset(next);
      setSaved(true);
      setEditing(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Kaydedilemedi.');
    } finally {
      setBusy(false);
    }
  }

  function cancel() {
    reset(data);
    setError(null);
    setEditing(false);
  }

  if (!editing) {
    return (
      <section className="card space-y-2 !p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="eyebrow">İndirim kuralı</h2>
            <span className={`badge ${data.enabled ? 'bg-success-50 text-success-700' : 'bg-sand-100 text-ink-500'}`}>
              {data.enabled ? 'Açık' : 'Kapalı'}
            </span>
          </div>
          <button
            type="button"
            className="btn-secondary btn-sm inline-flex items-center gap-1.5"
            onClick={() => {
              setSaved(false);
              setEditing(true);
            }}
          >
            <Pencil size={14} strokeWidth={1.5} aria-hidden />
            Düzenle
          </button>
        </div>
        <p className="text-sm">{data.summary}</p>
        {saved && <p className="text-sm text-success-700">Kaydedildi.</p>}
      </section>
    );
  }

  return (
    <section className="card space-y-3 !p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="eyebrow">İndirim kuralı</h2>
          <p className="muted mt-1 text-xs">
            Seçili günlerde, seçilen saatten önce başlayan randevulara sabit oranda indirim uygulanır.
            Başlangıç saati tam sınırdaysa (örn. 12:00) indirim yoktur.
          </p>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            className="h-4 w-4 accent-plum-600"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          {enabled ? 'Açık' : 'Kapalı'}
        </label>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className="label" htmlFor="discount-rate">
            İndirim oranı
          </label>
          <select
            id="discount-rate"
            className="field"
            value={rate}
            disabled={!enabled}
            onChange={(e) => setRate(Number(e.target.value))}
          >
            {RATES.map((r) => (
              <option key={r} value={r}>
                %{Math.round(r * 100)}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="label" htmlFor="discount-cutoff">
            Şu saatten önce başlayan randevular
          </label>
          <select
            id="discount-cutoff"
            className="field"
            value={cutoff}
            disabled={!enabled}
            onChange={(e) => setCutoff(Number(e.target.value))}
          >
            {data.cutoffChoices.map((m) => (
              <option key={m} value={m}>
                {minutesToLabel(m)}
              </option>
            ))}
          </select>
        </div>
      </div>

      <fieldset disabled={!enabled}>
        <legend className="label">Günler</legend>
        <div className="flex flex-wrap gap-3">
          {DAY_ORDER.map((d) => (
            <label key={d} className="flex cursor-pointer items-center gap-1.5 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4 accent-plum-600"
                checked={days.includes(d)}
                onChange={() => toggleDay(d)}
              />
              {data.dayNames[d]}
            </label>
          ))}
        </div>
      </fieldset>

      {error && <p className="alert alert-error">{error}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn-primary btn-sm"
          disabled={busy || !dirty || (enabled && days.length === 0)}
          onClick={save}
        >
          Kaydet
        </button>
        <button type="button" className="btn-ghost btn-sm" disabled={busy} onClick={cancel}>
          Vazgeç
        </button>
      </div>
    </section>
  );
}
