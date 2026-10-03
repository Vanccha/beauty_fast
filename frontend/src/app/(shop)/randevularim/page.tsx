import { ArrowRight, Link2, Users } from 'lucide-react';
import Link from 'next/link';
import { redirect } from 'next/navigation';

import { NameEditor } from '@/components/auth/NameEditor';
import { TierProgress } from '@/components/engagement/TierProgress';
import { formatTl } from '@/lib/api-client';
import { safeNext } from '@/lib/safe-next';
import { serverApi, type MeResponse } from '@/lib/server-api';
import { formatDateTr, minutesToLabel } from '@/lib/time';
import { AppointmentActions, GroupCancel, LogoutButton } from './actions';
import { DepositNotice, type CustomerDeposit } from '@/components/booking/DepositNotice';
import { appointmentLabel, appointmentTone } from '@/lib/appointment-status';
import { PrivacyPanel, type PrivacyStatus } from './privacy-panel';
import { ReviewForm } from './review-form';
import { VerifyGate } from './verify-gate';

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
  /** Randevuya 60 dakikadan az kaldı: iptal kapalı */
  cancelLocked: boolean;
  cancelLockedMessage: string;
  deposit: CustomerDeposit | null;
  hasReview: boolean;
  forCustomer: { id: number; firstName: string };
  bookedByMe: boolean;
  isMine: boolean;
  groupId: string | null;
}

interface MineResponse {
  upcoming: MineAppointment[];
  past: MineAppointment[];
}

interface AlbumResponse {
  photos: { id: number; imageUrl: string; note: string | null; colorTag: string | null }[];
}

export const dynamic = 'force-dynamic';

/** Aynı `groupId`'li randevuları yan yana toplar; sıra korunur. */
function groupUpcoming<T extends { groupId: string | null }>(list: T[]) {
  const out: { groupId: string | null; items: T[] }[] = [];
  for (const a of list) {
    const hit = a.groupId ? out.find((g) => g.groupId === a.groupId) : undefined;
    if (hit) hit.items.push(a);
    else out.push({ groupId: a.groupId, items: [a] });
  }
  return out;
}

/**
 * Randevu Sorgula — randevular, sadakat ilerlemesi ve kişisel albüm.
 *
 * Gizlilik: bu sayfa `CustomerNote` tablosunu HİÇ sorgulamaz. Gizli usta
 * notları yalnızca personel uçlarında görünür; müşteriye "paylaşılan"
 * notlar da bu sürümde gösterilmez (yanlışlıkla sızma riski sıfır).
 */
export default async function AppointmentsPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  // Veri FastAPI backend'inden gelir; bu sayfa veritabanını bilmez.
  const [me, { next }] = await Promise.all([
    serverApi<MeResponse>('/api/me'),
    searchParams,
  ]);
  const nextUrl = safeNext(next);

  // Oturum yok → telefon + kod. Doğrulamadan sonra `next` varsa oraya döner
  // (rezervasyonun eski "giriş yap, devam et" yolu bu sayede çalışır).
  if (!me.customer) return <VerifyGate next={nextUrl} />;
  if (nextUrl) redirect(nextUrl);

  const [mine, album, privacy] = await Promise.all([
    serverApi<MineResponse>('/api/appointments/mine'),
    serverApi<AlbumResponse>('/api/me/album'),
    serverApi<PrivacyStatus>('/api/me/privacy'),
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

  const renderUpcoming = (a: (typeof upcoming)[number]) => (
            <article key={a.id} className="card">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-medium tabular-nums">{formatDateTr(a.date)}</p>
                  <p className="muted tabular-nums">
                    {minutesToLabel(a.startMin)} – {minutesToLabel(a.endMin)} · {a.staff.name}
                  </p>
                  <p className="mt-1 text-sm">
                    {a.items.map((i) => i.service.name).join(' + ')}
                  </p>
                  <span className={`badge mt-2 ${appointmentTone(a.status, a.deposit?.status)}`}>
                    {appointmentLabel(a.status, a.deposit?.status)}
                  </span>
                  {a.bookedByMe && !a.isMine && (
                    <span className="badge ml-1.5 mt-2 bg-sand-100 text-ink-700">
                      Kimin için: {a.forCustomer.firstName}
                    </span>
                  )}
                  {a.isOpportunity && (
                    <span className="badge mt-2 bg-success-50 text-success-700">
                      Fırsat saati · %{Math.round(a.discountRate * 100)} indirim
                    </span>
                  )}
                </div>
                <span className="shrink-0 font-semibold tabular-nums">{formatTl(a.totalPrice)}</span>
              </div>

              {a.designRefs.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {a.designRefs.map((d) =>
                    d.source === 'UPLOAD' ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        key={d.id}
                        src={d.url}
                        alt="Tasarım referansı"
                        className="h-16 w-16 rounded-[2px] object-cover"
                      />
                    ) : (
                      <a
                        key={d.id}
                        href={d.url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="badge bg-sand-100 text-ink-700"
                      >
                        <Link2 size={14} strokeWidth={1.5} aria-hidden />
                        Referans bağlantısı
                      </a>
                    ),
                  )}
                </div>
              )}

              {a.deposit && (
                <div className="mt-4">
                  <DepositNotice deposit={a.deposit} />
                </div>
              )}

              <AppointmentActions
                appointmentId={a.id}
                version={a.version}
                cancelLocked={a.cancelLocked}
                cancelLockedMessage={a.cancelLockedMessage}
              />
            </article>
  );

  return (
    <div className="page-shell space-y-12 pb-12 pt-10 md:pt-14">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="eyebrow mb-2">Randevu Sorgula</p>
          <NameEditor firstName={fresh.firstName} />
        </div>
        <Link href="/randevu" className="btn-primary group">
          Yeni randevu al
          <ArrowRight
            size={16}
            strokeWidth={1.5}
            aria-hidden
            className="transition-transform duration-200 group-hover:translate-x-0.5"
          />
        </Link>
      </div>

      {/* ---------------- Yaklaşan ---------------- */}
      <section className="space-y-4">
        <div>
          <p className="eyebrow">Randevular</p>
          <h2 className="section-title mt-1">Yaklaşan randevularım</h2>
        </div>
        {upcoming.length === 0 ? (
          <div className="card">
            <p className="muted">Planlanmış randevun yok.</p>
            <Link href="/randevu" className="btn-primary group mt-4 w-full">
              Randevu al
              <ArrowRight
                size={16}
                strokeWidth={1.5}
                aria-hidden
                className="transition-transform duration-200 group-hover:translate-x-0.5"
              />
            </Link>
          </div>
        ) : (
          groupUpcoming(upcoming).map((g) =>
            g.groupId ? (
              <div key={g.groupId} className="space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="flex items-center gap-2 text-sm font-medium">
                    <Users size={16} strokeWidth={1.5} aria-hidden />
                    Grup randevusu · {formatDateTr(g.items[0].date)} {minutesToLabel(g.items[0].startMin)}
                  </p>
                  {g.items.some((x) => x.bookedByMe) &&
                    (g.items.some((x) => x.cancelLocked) ? (
                      <p className="muted text-xs">Randevuya 1 saatten az kaldığı için grup iptal edilemez.</p>
                    ) : (
                      <GroupCancel groupId={g.groupId} />
                    ))}
                </div>
                {g.items.map((a) => renderUpcoming(a))}
              </div>
            ) : (
              renderUpcoming(g.items[0])
            ),
          )
        )}
      </section>

      <TierProgress
        points={points}
        progress={tierProgress}
        optIn={fresh.engagementOptIn}
      />

      {/* ---------------- Albüm ---------------- */}
      {photos.length > 0 && (
        <section className="space-y-4">
          <div>
            <p className="eyebrow">Albüm</p>
            <h2 className="section-title mt-1">İşlem albümüm</h2>
          </div>
          <div className="grid grid-cols-3 gap-2">
            {photos.map((p) => (
              <figure key={p.id} className="overflow-hidden rounded-[2px] border border-sand-200 bg-white">
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
      <section className="space-y-4">
        <div>
          <p className="eyebrow">Geçmiş</p>
          <h2 className="section-title mt-1">Geçmiş randevularım</h2>
        </div>
        {past.length === 0 ? (
          <p className="muted">Henüz tamamlanmış randevun yok.</p>
        ) : (
          <ul className="space-y-3">
            {past.slice(0, 20).map((a) => (
              <li key={a.id} className="card">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium tabular-nums">{formatDateTr(a.date)}</p>
                    <p className="muted">{a.items.map((i) => i.service.name).join(' + ')}</p>
                    {a.bookedByMe && !a.isMine && (
                      <span className="badge mt-2 bg-sand-100 text-ink-700">
                        Kimin için: {a.forCustomer.firstName}
                      </span>
                    )}
                  </div>
                  <span className={`badge ${appointmentTone(a.status, a.deposit?.status)}`}>
                    {appointmentLabel(a.status, a.deposit?.status)}
                  </span>
                </div>
                {a.deposit && a.deposit.status !== 'NONE' && a.deposit.status !== 'AWAITING' && (
                  <div className="mt-2">
                    <DepositNotice deposit={a.deposit} compact />
                  </div>
                )}

                {/*
                  Değerlendirme yalnızca TAMAMLANMIŞ ve henüz yorumlanmamış
                  randevularda çıkar. Aynı kural sunucuda da uygulanır —
                  bu kontrol kolaylık içindir, güvenlik sınırı değil.
                */}
                {a.status === 'COMPLETED' &&
                  a.isMine &&
                  (a.review ? (
                    <p className="muted mt-3 border-t border-sand-200 pt-4">
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

      <details className="border-t border-sand-200 pt-6">
        <summary className="btn-link cursor-pointer list-none">Kişisel verilerim</summary>
        <div className="mt-6">
          <PrivacyPanel initial={privacy} />
        </div>
      </details>

      <div className="flex justify-center">
        <LogoutButton />
      </div>
    </div>
  );
}
