'use client';

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

export function AllergyEditor({
  customerId,
  allergies,
}: {
  customerId: number;
  allergies: { id: number; label: string }[];
}) {
  const { busy, error, run } = useAction();
  const [label, setLabel] = useState('');
  const [severity, setSeverity] = useState<'LOW' | 'MEDIUM' | 'HIGH'>('HIGH');
  const [note, setNote] = useState('');
  const [open, setOpen] = useState(false);

  if (!open) {
    return (
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn-secondary text-sm" onClick={() => setOpen(true)}>
          + Alerji ekle
        </button>
        {allergies.map((a) => (
          <button
            key={a.id}
            type="button"
            className="btn-ghost text-sm text-rose-700"
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
            ✕ {a.label}
          </button>
        ))}
      </div>
    );
  }

  return (
    <form
      className="mt-3 space-y-2 rounded-xl bg-white p-3"
      onSubmit={async (e) => {
        e.preventDefault();
        const okay = await run(() =>
          apiSend(`/api/admin/customers/${customerId}/allergy`, 'POST', {
            label,
            severity,
            note: note || undefined,
          }),
        );
        if (okay) {
          setLabel('');
          setNote('');
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
      {error && <p className="text-sm text-rose-600">{error}</p>}
      <div className="flex gap-2">
        <button type="button" className="btn-secondary flex-1" onClick={() => setOpen(false)}>
          Vazgeç
        </button>
        <button className="btn-primary flex-1" disabled={busy}>
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
        <button className="btn-primary ml-auto" disabled={busy || !body.trim()}>
          Not ekle
        </button>
      </div>
      {error && <p className="text-sm text-rose-600">{error}</p>}
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
      {error && <p className="text-sm text-rose-600 md:col-span-2">{error}</p>}
      <button className="btn-primary md:col-span-2" disabled={busy || !file}>
        {busy ? 'Yükleniyor…' : 'Albüme ekle'}
      </button>
    </form>
  );
}
