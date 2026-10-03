'use client';

import { Pencil } from 'lucide-react';
import { useState } from 'react';

import { ApiError, apiSend } from '@/lib/api-client';

export interface PostVisitSettingsData {
  enabled: boolean;
  delayHours: number;
  /** Kaydedilmiş özel metin; null ise varsayılan kullanılıyor. */
  message: string | null;
  defaultMessage: string;
  placeholders: Record<string, string>;
  maxLength: number;
  maxDelayHours: number;
  googleReviewUrl: string;
  instagramUrl: string;
  /** Örnek verilerle doldurulmuş hali — müşteriye giden metin. */
  preview: string;
}

/**
 * Ziyaret sonrası mesaj: randevu "Tamamlandı" olunca belirlenen süre sonra
 * müşteriye giden teşekkür + puanlama mesajı. İşlemseldir; indirim/kampanya
 * içermez, bu yüzden pazarlama onayı gerekmez (kural backend'de:
 * `services/post_visit.py`). Boş bırakılan bağlantının satırı mesajdan çıkar.
 */
export function PostVisitSettings({ initial }: { initial: PostVisitSettingsData }) {
  const [data, setData] = useState(initial);
  const [enabled, setEnabled] = useState(initial.enabled);
  const [delay, setDelay] = useState(String(initial.delayHours));
  const [message, setMessage] = useState(initial.message ?? initial.defaultMessage);
  const [google, setGoogle] = useState(initial.googleReviewUrl);
  const [instagram, setInstagram] = useState(initial.instagramUrl);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [editing, setEditing] = useState(false);
  const textareaId = 'post-visit-message';

  const delayNum = Number.parseInt(delay, 10);
  const delayValid = Number.isInteger(delayNum) && delayNum >= 0 && delayNum <= data.maxDelayHours;
  const dirty =
    enabled !== data.enabled ||
    delayNum !== data.delayHours ||
    message !== (data.message ?? data.defaultMessage) ||
    google !== data.googleReviewUrl ||
    instagram !== data.instagramUrl;

  function reset(from: PostVisitSettingsData) {
    setEnabled(from.enabled);
    setDelay(String(from.delayHours));
    setMessage(from.message ?? from.defaultMessage);
    setGoogle(from.googleReviewUrl);
    setInstagram(from.instagramUrl);
  }

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const next = await apiSend<PostVisitSettingsData>('/api/admin/messaging/post-visit', 'PUT', {
        enabled,
        delayHours: delayNum,
        message,
        googleReviewUrl: google.trim(),
        instagramUrl: instagram.trim(),
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
    setSaved(false);
    setEditing(false);
  }

  function insert(token: string) {
    const el = document.getElementById(textareaId) as HTMLTextAreaElement | null;
    if (!el) {
      setMessage((m) => m + token);
      return;
    }
    const start = el.selectionStart ?? message.length;
    const end = el.selectionEnd ?? message.length;
    setMessage(message.slice(0, start) + token + message.slice(end));
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + token.length, start + token.length);
    });
  }

  if (!editing) {
    return (
      <section className="card space-y-2 !p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="eyebrow">Ziyaret sonrası mesaj</h2>
            <span className={`badge ${data.enabled ? 'bg-success-50 text-success-700' : 'bg-sand-100 text-ink-500'}`}>
              {data.enabled ? `Açık · ${data.delayHours} saat sonra` : 'Kapalı'}
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
        <p className="muted line-clamp-2 whitespace-pre-line text-sm">{data.preview}</p>
        {saved && <p className="text-sm text-success-700">Kaydedildi.</p>}
      </section>
    );
  }

  return (
    <section className="card space-y-3 !p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="eyebrow">Ziyaret sonrası mesaj</h2>
          <p className="muted mt-1 text-xs">
            Randevu <strong>Tamamlandı</strong> olunca, belirlediğiniz süre sonra müşteriye teşekkür ve
            puanlama bağlantısı gönderilir. İndirim veya kampanya içermez.
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

      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label className="label" htmlFor="post-visit-delay">
            Kaç saat sonra
          </label>
          <input
            id="post-visit-delay"
            type="number"
            inputMode="numeric"
            min={0}
            max={data.maxDelayHours}
            className="field"
            value={delay}
            disabled={!enabled}
            aria-invalid={!delayValid}
            onChange={(e) => setDelay(e.target.value)}
          />
        </div>
        <div className="sm:col-span-1">
          <label className="label" htmlFor="post-visit-google">
            Google yorum bağlantısı
          </label>
          <input
            id="post-visit-google"
            type="url"
            className="field"
            placeholder="https://g.page/r/…/review"
            value={google}
            disabled={!enabled}
            onChange={(e) => setGoogle(e.target.value)}
          />
        </div>
        <div className="sm:col-span-1">
          <label className="label" htmlFor="post-visit-instagram">
            Instagram bağlantısı
          </label>
          <input
            id="post-visit-instagram"
            type="url"
            className="field"
            placeholder="https://instagram.com/salonunuz"
            value={instagram}
            disabled={!enabled}
            onChange={(e) => setInstagram(e.target.value)}
          />
        </div>
      </div>
      <p className="muted -mt-1 text-xs">
        Bir bağlantıyı boş bırakırsanız, o bağlantının geçtiği satır mesajdan çıkarılır.
        {(google.includes('ORNEK') || instagram.includes('ornek_salon')) && (
          <span className="text-brass-700">
            {' '}
            Şu an örnek (yer tutucu) bağlantı var; açmadan önce kendi bağlantılarınızı girin.
          </span>
        )}
      </p>

      <div>
        <label className="label" htmlFor={textareaId}>
          Mesaj
        </label>
        <textarea
          id={textareaId}
          className="field min-h-32"
          maxLength={data.maxLength}
          value={message}
          disabled={!enabled}
          onChange={(e) => setMessage(e.target.value)}
        />
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {Object.entries(data.placeholders).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className="btn-ghost btn-sm !px-2.5 !py-1 text-xs"
              disabled={!enabled}
              title={label}
              onClick={() => insert(key)}
            >
              {key}
            </button>
          ))}
          <span className="ml-auto text-xs tabular-nums text-ink-500">
            {message.length}/{data.maxLength}
          </span>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn-primary btn-sm"
          disabled={busy || !dirty || !delayValid}
          onClick={save}
        >
          Kaydet
        </button>
        {message !== data.defaultMessage && enabled && (
          <button
            type="button"
            className="btn-ghost btn-sm"
            disabled={busy}
            onClick={() => setMessage(data.defaultMessage)}
          >
            Varsayılan metne dön
          </button>
        )}
        <button type="button" className="btn-ghost btn-sm" disabled={busy} onClick={cancel}>
          Vazgeç
        </button>
        {error && <span className="text-sm text-danger-700">{error}</span>}
      </div>

      <div>
        <p className="label">Müşteriye giden mesaj (kayıtlı hali, örnek verilerle)</p>
        <p className="whitespace-pre-wrap rounded-[2px] border border-sand-200 bg-sand-50 px-3 py-2 text-sm text-ink-900">
          {data.preview}
        </p>
      </div>
    </section>
  );
}
