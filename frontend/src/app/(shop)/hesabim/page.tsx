import Link from 'next/link';
import { redirect } from 'next/navigation';

import { TierProgress } from '@/components/engagement/TierProgress';
import { formatTl } from '@/lib/api-client';
import { serverApi, type MeResponse } from '@/lib/server-api';
import { formatDateTr, minutesToLabel } from '@/lib/time';
import { AppointmentActions, LogoutButton } from './actions';
import { ReviewForm } from './review-form';

/** `GET /api/appointments/mine` içindeki tek randevu. */
interface MineAppointment {
  id: number;
  date: string;
  startMin: number;
  endMin: number;
  status: string;
  totalPrice: number;
  discountRate: number;
  isOpportunity: boolean;
  version: number;
  staff: { id: number; name: string; photoUrl: string | null };
  services: { id: number; name: string; price: number }[];
  designRefs: { id: number; source: string; url: string }[];
  cancellable: boolean;
  hasReview: boolean;
}

interface MineResponse {
  upcoming: MineAppointment[];
  past: MineAppointment[];
}

interface AlbumResponse {
  photos: { id: number; imageUrl: string; note: string | null; colorTag: string | null }[];
}

export const dynamic = 'force-dynamic';

/**
 * Hesabım — randevular, sadakat ilerlemesi ve kişisel albüm.
 *
 * Gizlilik: bu sayfa `CustomerNote` tablosunu HİÇ sorgulamaz. Gizli usta
 * notları yalnızca personel uçlarında görünür; müşteriye "paylaşılan"
 * notlar da bu sürümde gösterilmez (yanlışlıkla sızma riski sıfır).
 */
export default async function AccountPage() {
  // Veri FastAPI backend'inden gelir; bu sayfa veritabanını bilmez.
  const me = await serverApi<MeResponse>('/api/me');
  if (!me.customer) redirect('/giris?next=/hesabim');

  const [mine, album] = await Promise.all([
    serverApi<MineResponse>('/api/appointments/mine'),
    serverApi<AlbumResponse>('/api/me/album'),
  ]);

  // JSX aynı kalsın diye kalemler eski biçimde paketlenir.
  const shape = (a: MineAppointment) => ({
    ...a,
    items: a.services.map((service) => ({ service })),
    review: a.hasReview ? { id: a.id } : null,
  });

  const upcoming = mine.upcoming.map(shape);
  const past = mine.past.map(shape);
  const photos = album.photos;

  const points = me.customer.loyaltyPoints;
  const fresh = {
    firstName: me.customer.firstName,
    engagementOptIn: me.customer.engagementOptIn,
  };
  const tierProgress = me.welcome?.tierProgress ?? {
    current: me.customer.tier,
    next: null,
    pointsToNext: 0,
    ratio: 1,
    message: '',
  };

  return (
    <div className="page-shell space-y-5 pt-6">
      <div className="flex items-center justify-between">
        <h1 className="section-title">Merhaba {fresh.firstName}</h1>
        <LogoutButton />
      </div>

      <TierProgress
        points={points}
        progress={tierProgress}
        optIn={fresh.engagementOptIn}
      />

      {/* ---------------- Yaklaşan ---------------- */}
      <section className="space-y-2">
        <h2 className="section-title">Yaklaşan randevularım</h2>
        {upcoming.length === 0 ? (
          <div className="card">
            <p className="muted">Planlanmış randevun yok.</p>
            <Link href="/randevu" className="btn-primary mt-3 w-full">
              Randevu al
            </Link>
          </div>
        ) : (
          upcoming.map((a) => (
            <article key={a.id} className="card">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium">{formatDateTr(a.date)}</p>
                  <p className="muted">
                    {minutesToLabel(a.startMin)} – {minutesToLabel(a.endMin)} · {a.staff.name}
                  </p>
                  <p className="mt-1 text-sm">
                    {a.items.map((i) => i.service.name).join(' + ')}
                  </p>
                  {a.isOpportunity && (
                    <span className="badge mt-2 bg-emerald-50 text-emerald-700">
                      Fırsat saati · %{Math.round(a.discountRate * 100)} indirim
                    </span>
                  )}
                </div>
                <span className="shrink-0 font-semibold">{formatTl(a.totalPrice)}</span>
              </div>

              {a.designRefs.length > 0 && (
                <div className="mt-3 flex gap-2">
                  {a.designRefs.map((d) =>
                    d.source === 'UPLOAD' ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        key={d.id}
                        src={d.url}
                        alt="Tasarım referansı"
                        className="h-16 w-16 rounded-lg object-cover"
                      />
                    ) : (
                      <a
                        key={d.id}
                        href={d.url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="badge bg-sand-100 text-ink-700"
                      >
                        🔗 Referans bağlantısı
                      </a>
                    ),
                  )}
                </div>
              )}

              <AppointmentActions appointmentId={a.id} version={a.version} />
            </article>
          ))
        )}
      </section>

      {/* ---------------- Albüm ---------------- */}
      {photos.length > 0 && (
        <section className="space-y-2">
          <h2 className="section-title">İşlem albümüm</h2>
          <div className="grid grid-cols-3 gap-2">
            {photos.map((p) => (
              <figure key={p.id} className="overflow-hidden rounded-xl border border-sand-200 bg-white">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={p.imageUrl}
                  alt={p.note ?? 'İşlem fotoğrafı'}
                  loading="lazy"
                  className="aspect-square w-full object-cover"
                />
                {p.colorTag && (
                  <figcaption className="truncate px-2 py-1 text-[11px] text-ink-500">
                    {p.colorTag}
                  </figcaption>
                )}
              </figure>
            ))}
          </div>
        </section>
      )}

      {/* ---------------- Geçmiş ---------------- */}
      <section className="space-y-2">
        <h2 className="section-title">Geçmiş randevularım</h2>
        {past.length === 0 ? (
          <p className="muted">Henüz tamamlanmış randevun yok.</p>
        ) : (
          <ul className="space-y-2">
            {past.slice(0, 20).map((a) => (
              <li key={a.id} className="card">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">{formatDateTr(a.date)}</p>
                    <p className="muted">{a.items.map((i) => i.service.name).join(' + ')}</p>
                  </div>
                  <span
                    className={`badge ${
                      a.status === 'COMPLETED'
                        ? 'bg-emerald-50 text-emerald-700'
                        : a.status === 'NO_SHOW'
                          ? 'bg-rose-50 text-rose-700'
                          : 'bg-sand-100 text-ink-500'
                    }`}
                  >
                    {a.status === 'COMPLETED'
                      ? 'Tamamlandı'
                      : a.status === 'NO_SHOW'
                        ? 'Gelinmedi'
                        : 'İptal'}
                  </span>
                </div>

                {/*
                  Değerlendirme yalnızca TAMAMLANMIŞ ve henüz yorumlanmamış
                  randevularda çıkar. Aynı kural sunucuda da uygulanır —
                  bu kontrol kolaylık içindir, güvenlik sınırı değil.
                */}
                {a.status === 'COMPLETED' &&
                  (a.review ? (
                    <p className="muted mt-3 border-t border-sand-100 pt-3">
                      Bu randevuyu değerlendirdin. Teşekkürler!
                    </p>
                  ) : (
                    <ReviewForm
                      appointmentId={a.id}
                      serviceNames={a.items.map((i) => i.service.name).join(' + ')}
                    />
                  ))}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
