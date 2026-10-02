import { Star } from 'lucide-react';

import { Stars } from '@/components/marketing/Stars';
import { adminApi } from '@/lib/admin-api';
import type { ReviewSummary } from '@/lib/server-api';
import { formatDateTr, toDateKey } from '@/lib/time';
import { ReviewControls } from './review-controls';

export const dynamic = 'force-dynamic';

interface AdminReview {
  id: number;
  authorName: string;
  rating: number;
  comment: string;
  serviceNames: string | null;
  staffId: number | null;
  staffName: string | null;
  /** Yorumun dayandığı randevunun tarihi (YYYY-MM-DD) */
  appointmentDate: string | null;
  isVerified: boolean;
  isPublished: boolean;
  isFeatured: boolean;
  reply: string | null;
  createdAt: string;
}

interface AdminReviewsResponse {
  reviews: AdminReview[];
  summary: ReviewSummary;
  /** Yayında olup yanıtlanmamış düşük puanlı (≤3) yorumlar */
  pendingCount: number;
}

/**
 * Yorum yönetimi.
 *
 * Salonun vitrinini besleyen tablo burada yönetilir: uygunsuz yorumlar
 * yayından kaldırılır, en iyi yorumlar öne çıkarılır, müşteriye yanıt
 * yazılır. Yorumun kendisi düzenlenemez.
 *
 * Liste EN YENİDEN eskiye sıralanır ve yayından kaldırılmış olanlar da
 * görünür (soluk) — moderasyon kararı geri alınabilir olmalı.
 */
export default async function AdminReviewsPage() {
  // Son 100 yorum (yayından kaldırılanlar dahil) + özet FastAPI'den gelir.
  const { summary, reviews, pendingCount } =
    await adminApi<AdminReviewsResponse>('/api/admin/reviews');

  return (
    <div className="space-y-3">
      {/* Özet */}
      <div className="card flex flex-wrap items-center gap-x-8 gap-y-3 !p-4">
        <div>
          <p className="display text-2xl tabular-nums text-plum-700">
            {summary.average?.toFixed(2).replace('.', ',') ?? '—'}
          </p>
          <p className="muted">ortalama puan</p>
        </div>
        <div>
          <p className="display text-2xl tabular-nums">{summary.count}</p>
          <p className="muted">yayındaki yorum</p>
        </div>
        <div>
          <p className="display text-2xl tabular-nums">%{Math.round(summary.positiveRate * 100)}</p>
          <p className="muted flex items-center gap-1">
            4 <Star size={12} strokeWidth={1.5} aria-hidden /> ve üzeri
          </p>
        </div>
        {pendingCount > 0 && (
          <div className="rounded-[2px] border border-brass-300 px-3 py-2">
            <p className="text-sm font-semibold text-brass-700">
              {pendingCount} düşük puanlı yorum yanıtsız
            </p>
            <p className="text-xs text-ink-500">
              Yanıt vermek, okuyanlar için puandan daha çok şey anlatır.
            </p>
          </div>
        )}
      </div>

      {reviews.length === 0 ? (
        <p className="card muted !p-4">Henüz yorum yok.</p>
      ) : (
        <ul className="grid gap-2 lg:grid-cols-2">
          {reviews.map((review) => (
            <li
              key={review.id}
              className={`card !p-4 ${review.isPublished ? '' : 'opacity-60'}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-sm font-medium text-ink-900">{review.authorName}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <Stars value={review.rating} size="sm" />
                    <span className="text-xs text-ink-500">
                      {formatDateTr(toDateKey(new Date(review.createdAt)))}
                    </span>
                  </div>
                </div>

                <div className="flex shrink-0 flex-col items-end gap-1">
                  {!review.isPublished && (
                    <span className="badge border border-rose-300 bg-transparent text-rose-700">Yayında değil</span>
                  )}
                  {review.isFeatured && (
                    <span className="badge border border-plum-300 bg-transparent text-plum-700">Öne çıkan</span>
                  )}
                  {review.isVerified && (
                    <span className="badge border border-emerald-300 bg-transparent text-emerald-700">Doğrulanmış</span>
                  )}
                </div>
              </div>

              <p className="mt-2 text-sm leading-relaxed text-ink-700">{review.comment}</p>

              <p className="muted mt-2 text-xs">
                {review.serviceNames}
                {review.staffName && ` · ${review.staffName}`}
                {review.appointmentDate && ` · ${formatDateTr(review.appointmentDate)} randevusu`}
              </p>

              {review.reply && (
                <p className="mt-2 rounded-[2px] border border-sand-200 bg-sand-50 p-3 text-xs leading-relaxed text-ink-700">
                  <span className="font-semibold text-plum-700">Yanıtınız: </span>
                  {review.reply}
                </p>
              )}

              <ReviewControls
                id={review.id}
                isPublished={review.isPublished}
                isFeatured={review.isFeatured}
                reply={review.reply}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
