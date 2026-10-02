'use client';

import { useState } from 'react';

import { ReviewCard } from '@/components/marketing/ReviewCard';
import type { PublicReview } from '@/lib/server-api';

/** İlk görünümde gösterilen yorum sayısı. */
const INITIAL_COUNT = 6;

/** Vitrinde gösterilen en düşük puan. Özet (ortalama, dağılım) yine TÜM yorumlardan hesaplanır. */
const MIN_SHOWCASE_RATING = 4;

/**
 * Açılış sayfasındaki yorum listesi: yalnızca iyi (4–5 yıldız) yorumlar.
 * Mobilde yatay kaydırmalı şerit, masaüstünde sıkı ızgara olarak görünür.
 */
export function ReviewsBrowser({ reviews }: { reviews: PublicReview[] }) {
  const [expanded, setExpanded] = useState(false);

  const good = reviews.filter((r) => r.rating >= MIN_SHOWCASE_RATING);
  const visible = expanded ? good : good.slice(0, INITIAL_COUNT);

  if (good.length === 0) return null;

  return (
    <div>
      <ul className="-mx-5 flex snap-x snap-mandatory gap-3 overflow-x-auto px-5 pb-2 md:mx-0 md:grid md:grid-cols-3 md:overflow-visible md:px-0 md:pb-0">
        {visible.map((review) => (
          <li key={review.id} className="w-[84%] shrink-0 snap-center sm:w-[60%] md:w-auto">
            <ReviewCard review={review} compact />
          </li>
        ))}
      </ul>

      {!expanded && good.length > INITIAL_COUNT && (
        <div className="mt-4 text-center">
          <button type="button" onClick={() => setExpanded(true)} className="btn-secondary">
            Daha fazla göster ({good.length - INITIAL_COUNT})
          </button>
        </div>
      )}
    </div>
  );
}
