'use client';

import { useRouter } from 'next/navigation';
import { CircleCheck, Star, TriangleAlert } from 'lucide-react';
import { useState } from 'react';

import { ApiError, apiSend } from '@/lib/api-client';

/**
 * Tamamlanmış bir randevuyu değerlendirme formu.
 *
 * Açılış sayfasındaki yorumların kaynağı budur: vitrindeki her yorum
 * gerçek bir randevudan gelir. Form yalnızca `COMPLETED` durumundaki ve
 * henüz yorumlanmamış randevuların altında render edilir; sunucu tarafı
 * da aynı kuralı bağımsız olarak doğrular (`/api/reviews`).
 *
 * Yıldızlar radio input'tur: klavye ile ok tuşlarıyla gezilir, ekran
 * okuyucu "3 yıldız" der. Görsel yıldız `peer-checked` ile boyanır —
 * JavaScript kapalıyken bile seçim görünür kalır.
 */
export function ReviewForm({
  appointmentId,
  serviceNames,
}: {
  appointmentId: number;
  serviceNames: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiSend('/api/reviews', 'POST', { appointmentId, rating, comment: comment.trim() });
      setDone(true);
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Yorum gönderilemedi.');
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="alert alert-success mt-4" role="status">
        <CircleCheck size={16} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
        <p>Değerlendirmen için teşekkürler! Yorumun yayınlandı.</p>
      </div>
    );
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="btn-link mt-4"
      >
        Bu randevuyu değerlendir
      </button>
    );
  }

  const remaining = 10 - comment.trim().length;

  return (
    <form onSubmit={submit} className="mt-4 space-y-4 border-t border-sand-200 pt-4">
      <fieldset>
        <legend className="label">{serviceNames} — kaç yıldız?</legend>
        <div className="flex gap-1">
          {[1, 2, 3, 4, 5].map((star) => (
            <label key={star} className="cursor-pointer">
              <input
                type="radio"
                name={`rating-${appointmentId}`}
                value={star}
                checked={rating === star}
                onChange={() => setRating(star)}
                className="peer sr-only"
              />
              <span className="sr-only">{star} yıldız</span>
              <Star
                size={28}
                strokeWidth={1.5}
                aria-hidden
                className={`transition ${
                  star <= rating ? 'text-brass-500' : 'text-sand-300'
                } peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-plum-600`}
                fill="currentColor"
              />
            </label>
          ))}
        </div>
      </fieldset>

      <div>
        <label htmlFor={`comment-${appointmentId}`} className="label">
          Deneyimin
        </label>
        <textarea
          id={`comment-${appointmentId}`}
          className="field min-h-24"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          maxLength={1000}
          placeholder="Uygulama nasıldı? Başkalarına yardımcı olacak detaylar yazabilirsin."
        />
        <p className="muted mt-1">
          {remaining > 0
            ? `En az ${remaining} karakter daha`
            : `${comment.trim().length}/1000 karakter`}
        </p>
      </div>

      {error && (
        <div className="alert alert-danger" role="alert">
          <TriangleAlert size={16} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
          <p>{error}</p>
        </div>
      )}

      <p className="text-xs text-ink-500">
        Yorumun adının baş harfleriyle yayınlanır (örn. “Ayşe K.”).
      </p>

      <div className="flex gap-2">
        <button type="button" className="btn-secondary btn-sm flex-1" onClick={() => setOpen(false)}>
          Vazgeç
        </button>
        <button type="submit" className="btn-primary btn-sm flex-1" disabled={busy || remaining > 0}>
          {busy ? 'Gönderiliyor…' : 'Yorumu gönder'}
        </button>
      </div>
    </form>
  );
}
