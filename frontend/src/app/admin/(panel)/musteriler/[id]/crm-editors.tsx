'use client';

import { Plus, X } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ApiError, apiSend, apiUpload } from '@/lib/api-client';

/** Ortak hata/yükleniyor durumunu yöneten küçük yardımcı. */
function useAction() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      router.refresh();
      return true;
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'İşlem başarısız.');
      return false;
    } finally {
      setBusy(false);
    }
  };

  return { busy, error, run };
}

/* ------------------------------------------------------------------ */

/**
 * KVKK m.6: alerji sağlık verisidir. Müşterinin ilk alerji kaydında
 * personel açık rızayı aldığını işaretlemek zorundadır; sunucu da aynı
 * kuralı uygular (`CONSENT_REQUIRED`). Rıza bir kez kaydedildikten sonra
 * kutu gösterilmez.
 */
export function AllergyEditor({
  customerId,
  allergies,
  healthConsent,
}: {
  customerId: number;
  allergies: { id: number; label: string }[];
  healthConsent: boolean;
}) {
  const { busy, error, run } = useAction();
  const [label, setLabel] = useState('');
  const [severity, setSeverity] = useState<'LOW' | 'MEDIUM' | 'HIGH'>('HIGH');
  const [note, setNote] = useState('');
  const [consent, setConsent] = useState(false);
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn-secondary btn-sm" onClick={() => setOpen(true)}>
          <Plus size={14} strokeWidth={1.5} aria-hidden /> Alerji ekle
        </button>
        {allergies.map((a) => (
          <button
            key={a.id}
            type="button"
            className="btn-ghost btn-sm text-rose-700"
            disabled={busy}
            onClick={() =>
              void run(() =>
                apiSend(
                  `/api/admin/customers/${customerId}/allergy?allergyId=${a.id}`,
                  'DELETE',
                ),
              )
            }
          >
            <X size={14} strokeWidth={1.5} aria-hidden /> {a.label}
          </button>
        ))}
      </div>
    );
  }

  return (
    <form
      className="mt-3 space-y-2 rounded-[2px] border border-sand-200 bg-white p-3"
      onSubmit={async (e) => {
        e.preventDefault();
        const okay = await run(() =>
          apiSend(`/api/admin/customers/${customerId}/allergy`, 'POST', {
            label,
            severity,
            note: note || undefined,
            consentConfirmed: consent,
          }),
        );
        if (okay) {
          setLabel('');
          setNote('');
          setConsent(false);
          setOpen(false);
        }
      }}
    >
      <input
        className="field"
        value={label}
        onChange={(e) => setLabel(e.target.value)}
        placeholder="Örn. PPD (saç boyası)"
        required
      />
      <select
        className="field"
        value={severity}
        onChange={(e) => setSeverity(e.target.value as 'LOW' | 'MEDIUM' | 'HIGH')}
      >
        <option value="HIGH">Yüksek</option>
        <option value="MEDIUM">Orta</option>
        <option value="LOW">Düşük</option>
      </select>
      <input
        className="field"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Uygulama notu (isteğe bağlı)"
      />
      {!healthConsent && (
        <label className="flex items-start gap-2 rounded-[2px] border border-brass-300 bg-sand-100 p-3 text-sm text-ink-900">
          <input
            type="checkbox"
            className="mt-0.5 h-5 w-5 shrink-0 accent-plum-600"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
          />
          <span>
            Müşteriye{' '}
            <a href="/acik-riza#saglik" target="_blank" className="font-semibold underline">
              sağlık verisi açık rıza metnini
            </a>{' '}
            okuttum ve alerji bilgisinin kaydedilmesine <strong>açık rıza verdi</strong>.
          </span>
        </label>
      )}
      {error && <p className="text-sm text-danger-700">{error}</p>}
      <div className="flex gap-2">
        <button type="button" className="btn-secondary btn-sm flex-1" onClick={() => setOpen(false)}>
          Vazgeç
        </button>
        <button className="btn-primary btn-sm flex-1" disabled={busy || (!healthConsent && !consent)}>
          Kaydet
        </button>
      </div>
    </form>
  );
}

/* ------------------------------------------------------------------ */

export function NoteEditor({ customerId }: { customerId: number }) {
  const { busy, error, run } = useAction();
  const [body, setBody] = useState('');
  const [visibility, setVisibility] = useState<'STAFF_ONLY' | 'SHARED'>('STAFF_ONLY');

  return (
    <form
      className="mt-3 space-y-2"
      onSubmit={async (e) => {
        e.preventDefault();
        const okay = await run(() =>
          apiSend(`/api/admin/customers/${customerId}/note`, 'POST', { body, visibility }),
        );
        if (okay) setBody('');
      }}
    >
      <textarea
        className="field"
        rows={2}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Örn. Boya öncesi patch test yapılmalı."
        required
      />
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={visibility === 'STAFF_ONLY'}
            onChange={(e) => setVisibility(e.target.checked ? 'STAFF_ONLY' : 'SHARED')}
            className="h-5 w-5"
          />
          Yalnızca personel görsün
        </label>
        <button className="btn-primary btn-sm ml-auto" disabled={busy || !body.trim()}>
          Not ekle
        </button>
      </div>
      {error && <p className="text-sm text-danger-700">{error}</p>}
    </form>
  );
}

/* ------------------------------------------------------------------ */

/**
 * Albüm yükleyici.
 *
 * `colorTag` isteğe bağlı görünse de RENK EĞİLİMİ analizinin tek veri
 * kaynağıdır; bu yüzden sık kullanılan tonlar hazır seçenek olarak
 * sunulur (serbest metin de kabul edilir).
 */
const COLOR_SUGGESTIONS = [
  'nude', 'bej', 'kirmizi', 'bordo', 'pembe', 'lacivert', 'mor', 'siyah', 'kahve', 'sari',
];

export function PhotoUploader({ customerId }: { customerId: number }) {
  const { busy, error, run } = useAction();
  const [file, setFile] = useState<File | null>(null);
  const [colorTag, setColorTag] = useState('');
  const [note, setNote] = useState('');
  const [productInfo, setProductInfo] = useState('');

  return (
    <form
      className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!file) return;
        const form = new FormData();
        form.append('file', file);
        if (colorTag) form.append('colorTag', colorTag);
        if (note) form.append('note', note);
        if (productInfo) form.append('productInfo', productInfo);

        const okay = await run(() =>
          apiUpload(`/api/admin/customers/${customerId}/photo`, form),
        );
        if (okay) {
          setFile(null);
          setColorTag('');
          setNote('');
          setProductInfo('');
        }
      }}
    >
      <input
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="field"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <input
        className="field"
        list="color-tags"
        value={colorTag}
        onChange={(e) => setColorTag(e.target.value)}
        placeholder="Renk etiketi (renk eğilimi analizi için)"
      />
      <datalist id="color-tags">
        {COLOR_SUGGESTIONS.map((c) => (
          <option key={c} value={c} />
        ))}
      </datalist>
      <input
        className="field"
        value={productInfo}
        onChange={(e) => setProductInfo(e.target.value)}
        placeholder="Ürün / teknik (örn. kalici_oje no 42)"
      />
      <input
        className="field"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Not"
      />
      {error && <p className="text-sm text-danger-700 md:col-span-2">{error}</p>}
      <button className="btn-primary btn-sm md:col-span-2" disabled={busy || !file}>
        {busy ? 'Yükleniyor…' : 'Albüme ekle'}
      </button>
    </form>
  );
}
