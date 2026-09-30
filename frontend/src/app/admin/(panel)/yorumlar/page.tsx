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
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="section-title">Yorumlar</h1>
        <p className="muted">Son 100 yorum gösteriliyor</p>
      </div>

      {/* Özet */}
      <div className="card flex flex-wrap items-center gap-x-8 gap-y-3">
        <div>
          <p className="text-2xl font-semibold text-plum-700">
            {summary.average?.toFixed(2).replace('.', ',') ?? '—'}
          </p>
          <p className="muted">ortalama puan</p>
        </div>
        <div>
          <p className="text-2xl font-semibold">{summary.count}</p>
          <p className="muted">yayındaki yorum</p>
        </div>
        <div>
          <p className="text-2xl font-semibold">%{Math.round(summary.positiveRate * 100)}</p>
          <p className="muted">4★ ve üzeri</p>
        </div>
        {pendingCount > 0 && (
          <div className="rounded-xl bg-amber-50 px-4 py-2">
            <p className="text-sm font-semibold text-amber-800">
              {pendingCount} düşük puanlı yorum yanıtsız
            </p>
            <p className="text-xs text-amber-700">
              Yanıt vermek, okuyanlar için puandan daha çok şey anlatır.
            </p>
          </div>
        )}
      </div>

      {reviews.length === 0 ? (
        <p className="card muted">Henüz yorum yok.</p>
      ) : (
        <ul className="grid gap-3 lg:grid-cols-2">
          {reviews.map((review) => (
            <li
              key={review.id}
              className={`card ${review.isPublished ? '' : 'opacity-60'}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-medium">{review.authorName}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <Stars value={review.rating} size="sm" />
                    <span className="text-xs text-ink-500">
                      {formatDateTr(toDateKey(new Date(review.createdAt)))}
                    </span>
                  </div>
                </div>

                <div className="flex shrink-0 flex-col items-end gap-1">
                  {!review.isPublished && (
                    <span className="badge bg-rose-50 text-rose-700">Yayında değil</span>
                  )}
                  {review.isFeatured && (
                    <span className="badge bg-plum-100 text-plum-700">Öne çıkan</span>
                  )}
                  {review.isVerified && (
                    <span className="badge bg-emerald-50 text-emerald-700">Doğrulanmış</span>
                  )}
                </div>
              </div>

              <p className="mt-3 text-sm leading-relaxed text-ink-700">{review.comment}</p>

              <p className="muted mt-2">
                {review.serviceNames}
                {review.staffName && ` · ${review.staffName}`}
                {review.appointmentDate && ` · ${formatDateTr(review.appointmentDate)} randevusu`}
              </p>

              {review.reply && (
                <p className="mt-2 rounded-xl bg-sand-50 p-3 text-xs leading-relaxed text-ink-700">
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
