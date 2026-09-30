import type { PublicReview } from '@/lib/server-api';
import { Stars } from './Stars';

/**
 * Tek bir müşteri yorumu.
 *
 * Yazar avatarı olarak fotoğraf DEĞİL, baş harf kullanılır: yoruma
 * rastgele bir insan fotoğrafı iliştirmek, o kişinin gerçekten böyle
 * dediği izlenimi yaratır. Baş harf hem dürüst hem de sade.
 *
 * "Doğrulanmış randevu" rozeti yalnızca `isVerified` ise çıkar; bu alan
 * yorumun tamamlanmış bir randevuya bağlı olduğunu gösterir.
 */
export function ReviewCard({ review }: { review: PublicReview }) {
  const initials = review.authorName
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toLocaleUpperCase('tr');

  return (
    <figure className="flex h-full flex-col rounded-2xl border border-sand-200 bg-white p-5 shadow-sm">
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-plum-100 text-sm font-semibold text-plum-700"
        >
          {initials}
        </span>
        <div className="min-w-0">
          <figcaption className="truncate text-sm font-semibold">{review.authorName}</figcaption>
          <Stars value={review.rating} size="sm" className="mt-0.5" />
        </div>
      </div>

      <blockquote className="mt-4 flex-1 text-sm leading-relaxed text-ink-700">
        “{review.comment}”
      </blockquote>

      <div className="mt-4 space-y-2 border-t border-sand-100 pt-3">
        {review.serviceNames && (
          <p className="text-xs font-medium text-plum-700">{review.serviceNames}</p>
        )}
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-500">
          {review.staffName && <span>Uygulayan: {review.staffName}</span>}
          {review.isVerified && (
            <span className="inline-flex items-center gap-1 text-emerald-700">
              <svg viewBox="0 0 20 20" className="h-3.5 w-3.5" fill="currentColor" aria-hidden>
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.857-9.809a.75.75 0 00-1.214-.882l-3.483 4.79-1.88-1.88a.75.75 0 10-1.06 1.061l2.5 2.5a.75.75 0 001.137-.089l4-5.5z"
                  clipRule="evenodd"
                />
              </svg>
              Doğrulanmış randevu
            </span>
          )}
        </p>

        {review.reply && (
          <p className="rounded-xl bg-sand-50 p-3 text-xs leading-relaxed text-ink-700">
            <span className="font-semibold text-plum-700">Salon yanıtı: </span>
            {review.reply}
          </p>
        )}
      </div>
    </figure>
  );
}
