'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { apiSend } from '@/lib/api-client';

/**
 * Tek bir yorumun moderasyon kontrolleri.
 *
 * Yalnızca ÜÇ eylem vardır: yayından kaldır, öne çıkar, yanıtla.
 * Yorumun metni ve puanı burada düzenlenemez — bkz.
 * `/api/admin/reviews/[id]` başlığındaki gerekçe.
 */
export function ReviewControls({
  id,
  isPublished,
  isFeatured,
  reply,
}: {
  id: number;
  isPublished: boolean;
  isFeatured: boolean;
  reply: string | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(reply ?? '');

  async function patch(body: Record<string, unknown>) {
    setBusy(true);
    setError(null);
    try {
      await apiSend(`/api/admin/reviews/${id}`, 'PATCH', body);
      router.refresh();
      setEditing(false);
    } catch {
      setError('Güncelleme başarısız.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mt-3 space-y-2 border-t border-sand-100 pt-3">
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className="btn-secondary text-sm"
          disabled={busy}
          onClick={() => void patch({ isPublished: !isPublished })}
        >
          {isPublished ? 'Yayından kaldır' : 'Yayınla'}
        </button>

        <button
          type="button"
          className={isFeatured ? 'btn-secondary text-sm' : 'btn-ghost text-sm'}
          disabled={busy}
          onClick={() => void patch({ isFeatured: !isFeatured })}
        >
          {isFeatured ? '★ Öne çıkarıldı' : '☆ Öne çıkar'}
        </button>

        {!editing && (
          <button type="button" className="btn-ghost text-sm" onClick={() => setEditing(true)}>
            {reply ? 'Yanıtı düzenle' : 'Yanıtla'}
          </button>
        )}
      </div>

      {editing && (
        <div className="space-y-2">
          <textarea
            className="field min-h-20"
            value={draft}
            maxLength={600}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Müşteriye salon adına yanıt yaz…"
          />
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-secondary flex-1 text-sm"
              onClick={() => {
                setDraft(reply ?? '');
                setEditing(false);
              }}
            >
              Vazgeç
            </button>
            <button
              type="button"
              className="btn-primary flex-1 text-sm"
              disabled={busy}
              onClick={() => void patch({ reply: draft.trim() })}
            >
              {draft.trim() ? 'Yanıtı kaydet' : 'Yanıtı kaldır'}
            </button>
          </div>
        </div>
      )}

      {error && <p className="text-xs text-rose-600">{error}</p>}
    </div>
  );
}
