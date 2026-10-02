import { BadgeCheck } from 'lucide-react';

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
export function ReviewCard({
  review,
  compact = false,
}: {
  review: PublicReview;
  compact?: boolean;
}) {
  const initials = review.authorName
    .split(' ')
    .map((part) => part[0])
    .slice(0, 2)
    .join('')
    .toLocaleUpperCase('tr');

  return (
    <figure
      className={`flex h-full flex-col rounded-[4px] border border-sand-200 bg-white ${
        compact ? 'p-4' : 'p-6'
      }`}
    >
      <Stars value={review.rating} size="sm" />

      <blockquote
        className={`display flex-1 italic leading-relaxed text-ink-900 ${
          compact ? 'mt-2.5 text-[15px]' : 'mt-4 text-[17px]'
        }`}
      >
        “{review.comment}”
      </blockquote>

      <div className={`space-y-2 border-t border-sand-200 ${compact ? 'mt-4 pt-3' : 'mt-6 pt-4'}`}>
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-brass-300 text-xs font-semibold text-brass-700"
          >
            {initials}
          </span>
          <figcaption className="min-w-0 truncate text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-700">
            {review.authorName}
          </figcaption>
        </div>
        {review.serviceNames && (
          <p className="text-xs font-medium text-plum-700">{review.serviceNames}</p>
        )}
        <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink-500">
          {review.staffName && <span>Uygulayan: {review.staffName}</span>}
          {review.isVerified && (
            <span className="inline-flex items-center gap-1 text-success-700">
              <BadgeCheck size={14} strokeWidth={1.5} aria-hidden />
              Doğrulanmış randevu
            </span>
          )}
        </p>

        {review.reply && (
          <p className="rounded-[2px] border-l-2 border-brass-300 bg-sand-50 p-3 text-xs leading-relaxed text-ink-700">
            <span className="font-semibold text-plum-700">Salon yanıtı: </span>
            {review.reply}
          </p>
        )}
      </div>
    </figure>
  );
}
