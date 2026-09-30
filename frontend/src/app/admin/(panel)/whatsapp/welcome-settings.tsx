'use client';

import { useState } from 'react';

import { ApiError, apiSend } from '@/lib/api-client';

export interface WelcomeSettingsData {
  enabled: boolean;
  /** Kaydedilmiş özel metin; null ise varsayılan kullanılıyor. */
  message: string | null;
  defaultMessage: string;
  placeholders: Record<string, string>;
  maxLength: number;
  /** Yer tutucuları doldurulmuş hali — müşteriye giden metin. */
  preview: string;
  /** false ise sunucu gelen mesajları almıyor (EVOLUTION_WEBHOOK_URL yok). */
  inboundConfigured: boolean;
}

/**
 * İlk mesajda karşılama: salona WhatsApp'tan ilk kez yazan kişiye otomatik
 * gönderilen mesaj. Sistemin veya personelin daha önce yazıştığı kişilere
 * gitmez (kural backend'de: `services/whatsapp_inbound.py`).
 */
export function WelcomeSettings({ initial }: { initial: WelcomeSettingsData }) {
  const [data, setData] = useState(initial);
  const [enabled, setEnabled] = useState(initial.enabled);
  const [message, setMessage] = useState(initial.message ?? initial.defaultMessage);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const dirty = enabled !== data.enabled || message !== (data.message ?? data.defaultMessage);

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const next = await apiSend<WelcomeSettingsData>('/api/admin/messaging/welcome', 'PUT', {
        enabled,
        message,
      });
      setData(next);
      setMessage(next.message ?? next.defaultMessage);
      setSaved(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Kaydedilemedi.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">Karşılama mesajı</h2>
          <p className="muted">
            Salona WhatsApp&apos;tan <strong>ilk kez</strong> yazan kişiye otomatik gönderilir. Daha
            önce yazıştığınız, kod veya hatırlatma alan müşterilere gitmez.
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

      {!data.inboundConfigured && (
        <p className="rounded-xl bg-amber-50 px-3 py-2 text-sm text-amber-800">
          Sunucu gelen mesajları almıyor (<code>EVOLUTION_WEBHOOK_URL</code> tanımlı değil). Ayar
          kaydedilir ama karşılama mesajı gönderilmez.
        </p>
      )}

      <div>
        <label className="label" htmlFor="welcome-message">
          Mesaj
        </label>
        <textarea
          id="welcome-message"
          className="field min-h-32"
          maxLength={data.maxLength}
          value={message}
          disabled={!enabled}
          onChange={(e) => setMessage(e.target.value)}
        />
        <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs text-ink-500">
          <span>
            {Object.entries(data.placeholders).map(([key, label], i) => (
              <span key={key}>
                {i > 0 && ' · '}
                <code>{key}</code> {label.toLocaleLowerCase('tr-TR')}
              </span>
            ))}
          </span>
          <span className="tabular-nums">
            {message.length}/{data.maxLength}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-primary" disabled={busy || !dirty} onClick={save}>
          Kaydet
        </button>
        {message !== data.defaultMessage && enabled && (
          <button
            type="button"
            className="btn-ghost text-sm"
            disabled={busy}
            onClick={() => setMessage(data.defaultMessage)}
          >
            Varsayılan metne dön
          </button>
        )}
        {saved && !dirty && <span className="text-sm text-emerald-700">Kaydedildi.</span>}
        {error && <span className="text-sm text-rose-600">{error}</span>}
      </div>

      {data.enabled && (
        <div>
          <p className="label">Müşteriye giden mesaj (kayıtlı hali)</p>
          <p className="whitespace-pre-wrap rounded-xl bg-emerald-50 px-3 py-2 text-sm text-ink-900">
            {data.preview}
          </p>
        </div>
      )}
    </section>
  );
}
