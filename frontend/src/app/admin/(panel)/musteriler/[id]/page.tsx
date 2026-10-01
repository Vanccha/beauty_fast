import Link from 'next/link';
import { notFound } from 'next/navigation';

import { adminApi } from '@/lib/admin-api';
import { formatTl } from '@/lib/api-client';
import { ApiError } from '@/lib/server-api';
import { formatDateTr } from '@/lib/time';
import { AllergyEditor, NoteEditor, PhotoUploader } from './crm-editors';

export const dynamic = 'force-dynamic';

interface CustomerCard {
  profile: {
    id: number;
    firstName: string;
    lastName: string | null;
    phone: string;
    email: string | null;
    birthDate: string | null;
    engagementOptIn: boolean;
    /** KVKK: ticari ileti (tekrar hatırlatması) onayı */
    marketingConsent: boolean;
    /** KVKK m.6: alerji kaydı için açık rıza */
    healthConsent: boolean;
    loyaltyPoints: number;
    tier: string;
    tierProgress: {
      current: string;
      next: string | null;
      pointsToNext: number;
      ratio: number;
      message: string;
    };
    totalSpend: number;
    visitCount: number;
    noShowCount: number;
    lastVisitDaysAgo: number | null;
  };
  segment: {
    segment: string;
    badge: string;
    tone: string;
    showRate: number;
    warning: string | null;
  };
  /** KVKK: yalnızca toplulaştırılmış skor — başka salonun adı YOK */
  risk: { score: number; label: string; noShowRate: number; message: string };
  colors: {
    topColors: { tag: string; family: string; ratio: number }[];
    summary: string;
  };
  campaigns: { campaignId: number; name: string; kind: string; value: number; reasons: string[] }[];
  allergies: { id: number; label: string; severity: string; note: string | null }[];
  notes: {
    id: number;
    body: string;
    visibility: string;
    staffName: string | null;
    createdAt: string;
  }[];
  album: {
    id: number;
    imageUrl: string;
    note: string | null;
    colorTag: string | null;
    productInfo: string | null;
  }[];
  appointments: {
    id: number;
    date: string;
    startLabel: string;
    status: string;
    totalPrice: number;
    staffName: string;
    services: string[];
  }[];
}

const TONE_CLASS: Record<string, string> = {
  violet: 'bg-violet-50 text-violet-700',
  emerald: 'bg-emerald-50 text-emerald-700',
  red: 'bg-rose-50 text-rose-700',
  amber: 'bg-amber-50 text-amber-800',
  sky: 'bg-sky-50 text-sky-700',
  slate: 'bg-sand-100 text-ink-700',
};

const RISK_TONE: Record<string, string> = {
  DUSUK: 'bg-emerald-50 text-emerald-700',
  ORTA: 'bg-amber-50 text-amber-800',
  YUKSEK: 'bg-rose-50 text-rose-700',
  YETERSIZ_VERI: 'bg-sand-100 text-ink-500',
};

/**
 * ====================================================================
 * CRM KARTI
 * ====================================================================
 *
 * Bir ustanın müşteriye dokunmadan önce görmesi gereken her şey tek
 * ekranda: alerji ikazı (kırmızı kutu), segment rozeti, çapraz-salon
 * risk skoru, renk eğilimi, gizli notlar ve işlem albümü.
 *
 * KVKK: risk bölümü YALNIZCA skor/etiket/oran gösterir. Hangi salonda ne
 * olduğu ne veritabanından okunur ne de ekrana gelir.
 */
export default async function CustomerCardPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const customerId = Number(id);
  if (!Number.isInteger(customerId)) notFound();

  // CRM kartı FastAPI'den gelir; gizli notlar yalnızca bu personel ucunda döner.
  let card: CustomerCard;
  try {
    card = await adminApi<CustomerCard>(`/api/admin/customers/${customerId}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const profile = {
    ...card.profile,
    segment: card.segment,
    risk: card.risk,
    colors: card.colors,
    campaigns: card.campaigns,
  };
  const appointments = card.appointments.slice(0, 25);
  const notes = card.notes;
  const photos = card.album.slice(0, 24);
  const allergies = [...card.allergies].sort((a, b) => a.id - b.id);

  return (
    <div className="space-y-4">
      <Link href="/admin/musteriler" className="text-sm font-medium text-plum-700">
        ← Müşteri listesi
      </Link>

      {/* ---------------- Başlık ---------------- */}
      <header className="card">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold">
              {profile.firstName} {profile.lastName ?? ''}
            </h1>
            <p className="muted">0{profile.phone}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <span className={`badge ${TONE_CLASS[profile.segment.tone] ?? TONE_CLASS.slate}`}>
                {profile.segment.badge}
              </span>
              <span className="badge bg-sand-100 text-ink-700">{profile.tier}</span>
              <span className={`badge ${RISK_TONE[profile.risk.label] ?? RISK_TONE.YETERSIZ_VERI}`}>
                Risk: {profile.risk.label} ({profile.risk.score}/100)
              </span>
              <span
                className={`badge ${profile.marketingConsent ? 'bg-emerald-50 text-emerald-700' : 'bg-sand-100 text-ink-500'}`}
                title="Tekrar hatırlatmaları yalnızca onaylı müşterilere gönderilir"
              >
                {profile.marketingConsent ? 'İleti onayı var' : 'İleti onayı yok'}
              </span>
            </div>
            {profile.segment.warning && (
              <p className="mt-2 text-sm text-amber-800">{profile.segment.warning}</p>
            )}
          </div>

          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <dt className="muted">Toplam harcama</dt>
            <dd className="text-right font-semibold">{formatTl(profile.totalSpend)}</dd>
            <dt className="muted">Ziyaret</dt>
            <dd className="text-right font-semibold">{profile.visitCount}</dd>
            <dt className="muted">Gelmedi</dt>
            <dd className="text-right font-semibold">{profile.noShowCount}</dd>
            <dt className="muted">Puan</dt>
            <dd className="text-right font-semibold">{Math.round(profile.loyaltyPoints)}</dd>
          </dl>
        </div>

        <p className="mt-3 rounded-xl bg-sand-100 px-3 py-2 text-sm">
          {profile.tierProgress.message}
        </p>
      </header>

      {/* ---------------- ALERJİ (kırmızı kutu) ---------------- */}
      <section className="rounded-2xl border-2 border-rose-300 bg-rose-50 p-4">
        <h2 className="font-semibold text-rose-800">⚠️ Alerji ve hassasiyetler</h2>
        {allergies.length === 0 ? (
          <p className="mt-1 text-sm text-rose-700">Kayıtlı alerji yok.</p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm text-rose-800">
            {allergies.map((a) => (
              <li key={a.id}>
                <strong>{a.label}</strong> ({a.severity}){a.note ? ` — ${a.note}` : ''}
              </li>
            ))}
          </ul>
        )}
        <AllergyEditor
          customerId={customerId}
          allergies={allergies}
          healthConsent={profile.healthConsent}
        />
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* ---------------- Renk eğilimi ---------------- */}
        <section className="card">
          <h2 className="section-title">Renk eğilimi</h2>
          <p className="mt-1 text-sm">{profile.colors.summary}</p>
          {profile.colors.topColors.length > 0 && (
            <ul className="mt-3 space-y-2">
              {profile.colors.topColors.map((c) => (
                <li key={c.tag} className="text-sm">
                  <div className="flex justify-between">
                    <span>
                      {c.tag} <span className="muted">({c.family})</span>
                    </span>
                    <span className="tabular-nums">%{Math.round(c.ratio * 100)}</span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-sand-200">
                    <div
                      className="h-full rounded-full bg-plum-500"
                      style={{ width: `${Math.round(c.ratio * 100)}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-3 muted">
            Frekanslar zaman ağırlıklıdır: yakın tarihli tercihler eskilerden daha ağır sayılır.
          </p>
        </section>

        {/* ---------------- Kampanyalar ---------------- */}
        <section className="card">
          <h2 className="section-title">Eşleşen kampanyalar</h2>
          {profile.campaigns.length === 0 ? (
            <p className="mt-1 muted">Bu müşteri şu an hiçbir kampanya kuralına uymuyor.</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {profile.campaigns.map((c) => (
                <li key={c.campaignId} className="rounded-xl bg-sand-100 p-3 text-sm">
                  <p className="font-medium">
                    {c.name} —{' '}
                    {c.kind === 'DISCOUNT_PERCENT'
                      ? `%${c.value} indirim`
                      : c.kind === 'BONUS_POINTS'
                        ? `${c.value} bonus puan`
                        : 'Hediye hizmet'}
                  </p>
                  <p className="muted">Neden: {c.reasons.join(', ')}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>

      {/* ---------------- Gizli notlar ---------------- */}
      <section className="card">
        <h2 className="section-title">🔒 Usta notları</h2>
        <p className="muted">
          &quot;Yalnızca personel&quot; notları hiçbir müşteri ekranında veya API yanıtında görünmez.
        </p>
        <ul className="mt-3 space-y-2">
          {notes.map((n) => (
            <li key={n.id} className="rounded-xl border border-sand-200 p-3 text-sm">
              <p className="flex items-center gap-2">
                <span aria-hidden>{n.visibility === 'STAFF_ONLY' ? '🔒' : '👁️'}</span>
                {n.body}
              </p>
              <p className="mt-1 muted">
                {n.staffName ?? 'Sistem'} ·{' '}
                {new Date(n.createdAt).toLocaleDateString('tr-TR')}
              </p>
            </li>
          ))}
          {notes.length === 0 && <li className="muted">Henüz not yok.</li>}
        </ul>
        <NoteEditor customerId={customerId} />
      </section>

      {/* ---------------- Albüm ---------------- */}
      <section className="card">
        <h2 className="section-title">İşlem geçmişi albümü</h2>
        <PhotoUploader customerId={customerId} />
        {photos.length === 0 ? (
          <p className="mt-3 muted">Henüz fotoğraf yok.</p>
        ) : (
          <div className="mt-3 grid grid-cols-3 gap-2 md:grid-cols-6">
            {photos.map((p) => (
              <figure key={p.id} className="overflow-hidden rounded-xl border border-sand-200">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={p.imageUrl}
                  alt={p.note ?? ''}
                  loading="lazy"
                  className="aspect-square w-full object-cover"
                />
                <figcaption className="px-2 py-1 text-[10px] text-ink-500">
                  {p.colorTag ?? '—'}
                </figcaption>
              </figure>
            ))}
          </div>
        )}
      </section>

      {/* ---------------- Randevu geçmişi ---------------- */}
      <section className="card">
        <h2 className="section-title">Randevu geçmişi</h2>
        <ul className="mt-2 divide-y divide-sand-100">
          {appointments.map((a) => (
            <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <div>
                <p className="font-medium">
                  {formatDateTr(a.date)} · {a.startLabel}
                </p>
                <p className="muted">
                  {a.services.join(' + ')} · {a.staffName}
                </p>
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`badge ${
                    a.status === 'COMPLETED'
                      ? 'bg-emerald-50 text-emerald-700'
                      : a.status === 'NO_SHOW'
                        ? 'bg-rose-50 text-rose-700'
                        : a.status === 'CANCELLED'
                          ? 'bg-sand-100 text-ink-500'
                          : 'bg-sky-50 text-sky-700'
                  }`}
                >
                  {a.status}
                </span>
                <span className="font-medium">{formatTl(a.totalPrice)}</span>
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
