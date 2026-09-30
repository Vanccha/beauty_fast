import Link from 'next/link';

import { ReviewCard } from '@/components/marketing/ReviewCard';
import { Stars } from '@/components/marketing/Stars';
import {
  serverApi,
  type PublicReview,
  type ReviewSummary,
} from '@/lib/server-api';

export const dynamic = 'force-dynamic';

interface ReviewsResponse {
  summary: ReviewSummary;
  items: PublicReview[];
}

interface ShowcaseTeam {
  team: { id: number; name: string }[];
}

/**
 * Tüm müşteri yorumları — herkese açık (üyelik gerekmez).
 *
 * Filtreler URL üzerinden çalışır (`?puan=5`, `?usta=3`); böylece
 * istemci JavaScript'i olmadan da gezilebilir ve bağlantı paylaşılabilir.
 * Portfolyo sayfasıyla aynı desen.
 *
 * Bu sayfa yorumları TARİH sırasına göre listeler — açılış sayfasındaki
 * vitrin sıralaması (öne çıkanlar önce) burada kullanılmaz. Vitrin en
 * iyisini gösterir, bu sayfa olanı gösterir.
 */
export default async function ReviewsPage({
  searchParams,
}: {
  searchParams: Promise<{ puan?: string; usta?: string }>;
}) {
  const { puan, usta } = await searchParams;

  const minRating = puan && /^[1-5]$/.test(puan) ? Number(puan) : undefined;
  const staffId = usta && /^\d+$/.test(usta) ? Number(usta) : undefined;

  const query = new URLSearchParams();
  if (minRating) query.set('minRating', String(minRating));
  if (staffId) query.set('staffId', String(staffId));

  // Filtreler backend'de uygulanır; özet her zaman TÜM yorumları özetler.
  const [filtered, showcase] = await Promise.all([
    serverApi<ReviewsResponse>(`/api/reviews?${query.toString()}`),
    serverApi<ShowcaseTeam>('/api/showcase'),
  ]);

  const summary = filtered.summary;
  const reviews = filtered.items;
  const staff = showcase.team;

  /** Aktif filtreleri koruyarak bağlantı üretir. */
  const linkTo = (next: { puan?: number; usta?: number }) => {
    const params = new URLSearchParams();
    const rating = next.puan ?? minRating;
    const staffFilter = next.usta ?? staffId;
    if (rating) params.set('puan', String(rating));
    if (staffFilter) params.set('usta', String(staffFilter));
    const query = params.toString();
    return query ? `/yorumlar?${query}` : '/yorumlar';
  };

  return (
    <div className="page-shell space-y-6 pt-6">
      <header>
        <p className="eyebrow">Değerlendirmeler</p>
        <h1 className="display mt-2 text-2xl md:text-3xl">Müşteri yorumları</h1>
        <p className="muted mt-2 max-w-2xl">
          Yorumların tamamı, salonda tamamlanmış bir randevusu olan müşteriler tarafından
          yazılmıştır. Puanlar düzenlenmez veya seçilerek gösterilmez.
        </p>
      </header>

      {summary.count === 0 ? (
        <p className="card">Henüz yayınlanmış bir yorum yok.</p>
      ) : (
        <>
          {/* Özet şerit */}
          <div className="card flex flex-wrap items-center gap-x-8 gap-y-4">
            <div>
              <div className="flex items-baseline gap-2">
                <span className="display text-4xl text-plum-700">
                  {summary.average?.toFixed(1).replace('.', ',')}
                </span>
                <span className="text-sm text-ink-500">/ 5</span>
              </div>
              <Stars value={summary.average ?? 0} className="mt-1" />
            </div>

            <ul className="flex-1 space-y-1.5">
              {([5, 4, 3, 2, 1] as const).map((star) => {
                const value = summary.distribution[star];
                const ratio = (value / summary.count) * 100;
                return (
                  <li key={star} className="flex items-center gap-2 text-xs text-ink-500">
                    <span className="w-3 tabular-nums">{star}</span>
                    <span aria-hidden className="text-amber-400">
                      ★
                    </span>
                    <span
                      aria-hidden
                      className="h-1.5 flex-1 overflow-hidden rounded-full bg-sand-100"
                    >
                      <span
                        className="block h-full rounded-full bg-plum-500"
                        style={{ width: `${ratio}%` }}
                      />
                    </span>
                    <span className="w-8 text-right tabular-nums">{value}</span>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* Filtreler — JavaScript'siz çalışır */}
          <div className="space-y-2">
            <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
              <FilterChip href={linkTo({ puan: undefined })} active={!minRating}>
                Tüm puanlar
              </FilterChip>
              {([5, 4, 3] as const).map((star) => (
                <FilterChip key={star} href={linkTo({ puan: star })} active={minRating === star}>
                  {star}★ ve üzeri
                </FilterChip>
              ))}
            </div>

            <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
              <FilterChip href={minRating ? `/yorumlar?puan=${minRating}` : '/yorumlar'} active={!staffId}>
                Tüm ekip
              </FilterChip>
              {staff.map((member) => (
                <FilterChip
                  key={member.id}
                  href={linkTo({ usta: member.id })}
                  active={staffId === member.id}
                >
                  {member.name}
                </FilterChip>
              ))}
            </div>
          </div>

          {reviews.length === 0 ? (
            <p className="card">
              Bu filtreye uyan yorum yok.{' '}
              <Link href="/yorumlar" className="font-medium text-plum-700">
                Filtreyi temizle
              </Link>
            </p>
          ) : (
            <>
              <p className="muted">{reviews.length} yorum gösteriliyor</p>
              <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {reviews.map((review) => (
                  <li key={review.id}>
                    <ReviewCard review={review} />
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}

      <div className="card bg-plum-50/60 text-center">
        <p className="font-semibold">Sen de değerlendirmek ister misin?</p>
        <p className="muted mx-auto mt-1 max-w-md">
          Tamamlanan randevularına Hesabım sayfasından puan verebilir, yorumunu yazabilirsin.
        </p>
        <Link href="/hesabim" className="btn-primary mt-4">
          Hesabıma git
        </Link>
      </div>
    </div>
  );
}

/** URL tabanlı filtre etiketi (portfolyo sayfasındaki desenle aynı). */
function FilterChip({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      aria-current={active ? 'true' : undefined}
      className={`touch-target inline-flex shrink-0 items-center rounded-full border px-4 text-sm font-medium ${
        active
          ? 'border-plum-600 bg-plum-600 text-white'
          : 'border-sand-300 bg-white text-ink-700 hover:bg-sand-100'
      }`}
    >
      {children}
    </Link>
  );
}
