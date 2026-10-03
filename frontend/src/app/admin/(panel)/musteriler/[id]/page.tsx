import { AlertTriangle, ChevronDown, ChevronLeft, Eye, Lock } from 'lucide-react';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import { adminApi } from '@/lib/admin-api';
import {
  appointmentDot,
  appointmentLabel,
  appointmentTone,
  depositBadge,
} from '@/lib/appointment-status';
import { formatTl } from '@/lib/api-client';
import { formatPhone } from '@/lib/phone';
import { ApiError } from '@/lib/server-api';
import { formatDateTr, parseDateKey } from '@/lib/time';
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
    depositStatus?: string;
    totalPrice: number;
    staffName: string;
    services: string[];
  }[];
}

const TONE_CLASS: Record<string, string> = {
  violet: 'border border-plum-300 bg-transparent text-plum-700',
  emerald: 'border border-emerald-300 bg-transparent text-emerald-700',
  red: 'border border-rose-300 bg-transparent text-rose-700',
  amber: 'border border-brass-300 bg-transparent text-brass-700',
  sky: 'border border-sand-300 bg-transparent text-ink-700',
  slate: 'border border-sand-200 bg-sand-100 text-ink-700',
};

const RISK_TONE: Record<string, string> = {
  DUSUK: 'border border-emerald-300 bg-transparent text-emerald-700',
  ORTA: 'border border-brass-300 bg-transparent text-brass-700',
  YUKSEK: 'border border-rose-300 bg-transparent text-rose-700',
  YETERSIZ_VERI: 'border border-sand-200 bg-sand-100 text-ink-500',
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
  const history = [...card.appointments]
    .sort((x, y) => `${y.date} ${y.startLabel}`.localeCompare(`${x.date} ${x.startLabel}`))
    .slice(0, 50);
  const notes = card.notes;
  const photos = card.album.slice(0, 24);
  const allergies = [...card.allergies].sort((a, b) => a.id - b.id);

  return (
    <div className="space-y-3">
      <Link
        href="/admin/musteriler"
        className="inline-flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-plum-700"
      >
        <ChevronLeft size={14} strokeWidth={1.5} aria-hidden /> Müşteri listesi
      </Link>

      {/* ---------------- Başlık ---------------- */}
      <header className="card !p-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h1 className="display text-xl text-ink-900">
              {profile.firstName} {profile.lastName ?? ''}
            </h1>
            <p className="muted tabular-nums">{formatPhone(profile.phone)}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <span className={`badge ${TONE_CLASS[profile.segment.tone] ?? TONE_CLASS.slate}`}>
                {profile.segment.badge}
              </span>
              <span className="badge border border-sand-200 bg-sand-100 text-ink-700">{profile.tier}</span>
              <span className={`badge ${RISK_TONE[profile.risk.label] ?? RISK_TONE.YETERSIZ_VERI}`}>
                Risk: {profile.risk.label} ({profile.risk.score}/100)
              </span>
              <span
                className={`badge ${profile.marketingConsent ? 'border border-emerald-300 bg-transparent text-emerald-700' : 'border border-sand-200 bg-sand-100 text-ink-500'}`}
                title="Tekrar hatırlatmaları yalnızca onaylı müşterilere gönderilir"
              >
                {profile.marketingConsent ? 'İleti onayı var' : 'İleti onayı yok'}
              </span>
            </div>
            {profile.segment.warning && (
              <p className="mt-2 text-sm text-brass-700">{profile.segment.warning}</p>
            )}
          </div>

          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm tabular-nums">
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

        <p className="mt-3 rounded-[2px] bg-sand-100 px-3 py-2 text-sm">
          {profile.tierProgress.message}
        </p>
      </header>

      {/* ---------------- ALERJİ (kırmızı kutu) ---------------- */}
      <section className="rounded-[4px] border border-rose-300 p-4">
        <h2 className="eyebrow flex items-center gap-1.5 !text-rose-700">
          <AlertTriangle size={14} strokeWidth={1.5} aria-hidden />
          Alerji ve hassasiyetler
        </h2>
        {allergies.length === 0 ? (
          <p className="mt-1 muted">Kayıtlı alerji yok.</p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm text-rose-700">
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

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {/* ---------------- Renk eğilimi ---------------- */}
        <section className="card !p-4">
          <h2 className="eyebrow">Renk eğilimi</h2>
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
                  <div className="mt-1 h-1 rounded-[1px] bg-sand-200">
                    <div
                      className="h-full rounded-[1px] bg-plum-500"
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
        <section className="card !p-4">
          <h2 className="eyebrow">Eşleşen kampanyalar</h2>
          {profile.campaigns.length === 0 ? (
            <p className="mt-1 muted">Bu müşteri şu an hiçbir kampanya kuralına uymuyor.</p>
          ) : (
            <ul className="mt-2 space-y-2">
              {profile.campaigns.map((c) => (
                <li key={c.campaignId} className="rounded-[2px] border border-sand-200 p-3 text-sm">
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
      <section className="card !p-4">
        <h2 className="eyebrow flex items-center gap-1.5">
          <Lock size={14} strokeWidth={1.5} aria-hidden />
          Notlar
        </h2>
        <ul className="mt-3 space-y-2">
          {notes.map((n) => (
            <li key={n.id} className="rounded-[2px] border border-sand-200 p-3 text-sm">
              <p className="flex items-center gap-2">
                {n.visibility === 'STAFF_ONLY' ? (
                  <Lock size={14} strokeWidth={1.5} className="shrink-0 text-ink-500" aria-hidden />
                ) : (
                  <Eye size={14} strokeWidth={1.5} className="shrink-0 text-ink-500" aria-hidden />
                )}
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
      <section className="card !p-4">
        <h2 className="eyebrow">İşlem geçmişi albümü</h2>
        <PhotoUploader customerId={customerId} />
        {photos.length === 0 ? (
          <p className="mt-3 muted">Henüz fotoğraf yok.</p>
        ) : (
          <div className="mt-3 grid grid-cols-3 gap-2 md:grid-cols-6">
            {photos.map((p) => (
              <figure key={p.id} className="overflow-hidden rounded-[2px] border border-sand-200">
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
      <section className="card !p-4">
        <h2 className="eyebrow">Randevu geçmişi</h2>
        {history.length === 0 ? (
          <p className="muted mt-2">Henüz randevu yok.</p>
        ) : (
          <div className="mt-2 space-y-1">
            {history.slice(0, 8).map((a) => (
              <AppointmentRow key={a.id} a={a} />
            ))}
            {history.length > 8 && (
              <details className="group/all">
                <summary className="muted cursor-pointer list-none rounded-xl px-3 py-2 text-center text-sm font-medium hover:bg-sand-50 group-open/all:hidden [&::-webkit-details-marker]:hidden">
                  Tümünü göster ({history.length})
                </summary>
                <div className="space-y-1">
                  {history.slice(8).map((a) => (
                    <AppointmentRow key={a.id} a={a} />
                  ))}
                </div>
              </details>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

const SHORT_MONTHS = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'];

function formatShortDate(key: string): string {
  const d = parseDateKey(key);
  return `${d.getDate()} ${SHORT_MONTHS[d.getMonth()]} ${d.getFullYear()}`;
}

function AppointmentRow({
  a,
}: {
  a: {
    id: number;
    date: string;
    startLabel: string;
    staffName: string;
    services: string[];
    status: string;
    depositStatus?: string;
    totalPrice: number;
  };
}) {
  const first = a.services[0] ?? 'Randevu';
  const more = a.services.length - 1;
  return (
    <details className="group rounded-xl border border-transparent open:border-sand-200 open:bg-sand-50/50">
      <summary className="flex cursor-pointer list-none items-center gap-3 rounded-xl px-3 py-2.5 text-sm hover:bg-sand-50 [&::-webkit-details-marker]:hidden">
        <span className="min-w-0 flex-1 truncate font-medium">
          {first}
          {more > 0 && <span className="muted"> +{more}</span>}
        </span>
        <span className="muted shrink-0 tabular-nums">{formatShortDate(a.date)}</span>
        <span
          className={`h-2 w-2 shrink-0 rounded-full ${appointmentDot(a.status, a.depositStatus)}`}
          title={appointmentLabel(a.status, a.depositStatus)}
          aria-label={appointmentLabel(a.status, a.depositStatus)}
        />
        <ChevronDown
          size={16}
          strokeWidth={1.5}
          className="shrink-0 text-ink-500 transition-transform group-open:rotate-180"
          aria-hidden
        />
      </summary>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 px-3 pb-3 pt-1 text-sm">
        <dt className="muted">Tarih</dt>
        <dd className="tabular-nums">
          {formatDateTr(a.date)} · {a.startLabel}
        </dd>
        <dt className="muted">Personel</dt>
        <dd>{a.staffName}</dd>
        <dt className="muted">Hizmetler</dt>
        <dd>{a.services.join(' + ')}</dd>
        <dt className="muted">Durum</dt>
        <dd>
          <span className={`badge ${appointmentTone(a.status, a.depositStatus)}`}>
            {appointmentLabel(a.status, a.depositStatus)}
          </span>
          {depositBadge(a.depositStatus) && (
            <span className={`badge ml-1.5 ${depositBadge(a.depositStatus)?.tone}`}>
              {depositBadge(a.depositStatus)?.label}
            </span>
          )}
        </dd>
        <dt className="muted">Ücret</dt>
        <dd className="font-medium tabular-nums">{formatTl(a.totalPrice)}</dd>
      </dl>
    </details>
  );
}
