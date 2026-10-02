import { adminApi } from '@/lib/admin-api';
import { CampaignToggle } from './campaign-toggle';

export const dynamic = 'force-dynamic';

/** Kampanya hedefleme kuralı (FastAPI JSON'u çözümlenmiş olarak döner). */
interface TargetRule {
  minTier?: string;
  maxTier?: string;
  segments?: string[];
  minTotalSpend?: number;
  maxTotalSpend?: number;
  minVisits?: number;
  maxVisits?: number;
  minPoints?: number;
  maxRiskScore?: number;
  minDaysSinceLastVisit?: number;
  maxDaysSinceLastVisit?: number;
  anyServiceIds?: number[];
  birthdayMonth?: boolean;
}

interface CampaignRow {
  id: number;
  name: string;
  description: string | null;
  kind: string;
  value: number;
  targetRule: TargetRule;
  priority: number;
  isActive: boolean;
  startsAt: string | null;
  endsAt: string | null;
  grantCount: number;
  /** Şu anda kurala uyan müşteri sayısı (gerçek profillerle) */
  matchedCount: number;
}

interface CampaignsResponse {
  campaigns: CampaignRow[];
  customerCount: number;
}

/** Hedefleme kuralını insan diline çevirir. */
function describeRule(rule: TargetRule): string[] {
  const out: string[] = [];
  if (rule.minTier) out.push(`en az ${rule.minTier} seviye`);
  if (rule.maxTier) out.push(`en fazla ${rule.maxTier} seviye`);
  if (rule.segments?.length) out.push(`segment: ${rule.segments.join(' / ')}`);
  if (rule.minTotalSpend) out.push(`toplam harcama ≥ ${rule.minTotalSpend} TL`);
  if (rule.maxTotalSpend) out.push(`toplam harcama ≤ ${rule.maxTotalSpend} TL`);
  if (rule.minVisits) out.push(`≥ ${rule.minVisits} ziyaret`);
  if (rule.maxVisits) out.push(`≤ ${rule.maxVisits} ziyaret`);
  if (rule.minPoints) out.push(`≥ ${rule.minPoints} puan`);
  if (rule.maxRiskScore !== undefined) out.push(`risk skoru ≤ ${rule.maxRiskScore}`);
  if (rule.minDaysSinceLastVisit) out.push(`son ziyaret ≥ ${rule.minDaysSinceLastVisit} gün önce`);
  if (rule.maxDaysSinceLastVisit) out.push(`son ziyaret ≤ ${rule.maxDaysSinceLastVisit} gün önce`);
  if (rule.birthdayMonth) out.push('doğum günü ayında');
  return out.length ? out : ['koşulsuz (herkes)'];
}

/**
 * ====================================================================
 * KAMPANYALAR — algoritmik hedefleme
 * ====================================================================
 *
 * Manuel kupon kodu YOKTUR. Her kampanya bir JSON kuralıdır; motor
 * (`matchesRule`) müşteri profilini kurala göre değerlendirir.
 *
 * Bu sayfa kuralı hem insan diline çevirir hem de "şu anda kaç müşteri
 * eşleşiyor" sayısını GERÇEK profillerle hesaplar — yönetici kuralı
 * yayınlamadan önce kapsamını görür.
 */
export default async function CampaignsPage() {
  // Kapsam sayısı FastAPI'de, müşteri profilleri üzerinde hesaplanır.
  const { campaigns, customerCount } = await adminApi<CampaignsResponse>('/api/admin/campaigns');

  return (
    <div className="space-y-3">
      <p className="muted">
        Kupon kodu yok — kampanyalar müşteri profiline göre otomatik eşleşir.
      </p>

      <div className="space-y-2">
        {campaigns.map((c) => {
          const rule = c.targetRule;
          const matched = c.matchedCount;

          return (
            <article key={c.id} className="card !p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold text-ink-900">
                    {c.name}
                    {!c.isActive && (
                      <span className="badge ml-2 border border-sand-200 bg-sand-100 text-ink-500">pasif</span>
                    )}
                  </h2>
                  {c.description && <p className="muted">{c.description}</p>}
                </div>

                <div className="flex items-center gap-2">
                  <span className="badge border border-plum-300 bg-transparent text-plum-700">
                    {c.kind === 'DISCOUNT_PERCENT'
                      ? `%${c.value} indirim`
                      : c.kind === 'BONUS_POINTS'
                        ? `${c.value} bonus puan`
                        : 'Hediye hizmet'}
                  </span>
                  <CampaignToggle id={c.id} isActive={c.isActive} />
                </div>
              </div>

              <dl className="mt-3 grid grid-cols-1 gap-2 text-sm md:grid-cols-3">
                <div className="rounded-[2px] border border-sand-200 p-3">
                  <dt className="eyebrow">Hedefleme kuralı</dt>
                  <dd className="mt-1">
                    <ul className="space-y-0.5">
                      {describeRule(rule).map((r) => (
                        <li key={r}>• {r}</li>
                      ))}
                    </ul>
                  </dd>
                </div>
                <div className="rounded-[2px] border border-sand-200 p-3">
                  <dt className="eyebrow">Şu anda eşleşen</dt>
                  <dd className="mt-1 display text-2xl tabular-nums">
                    {matched}{' '}
                    <span className="text-sm font-normal">/ {customerCount} müşteri</span>
                  </dd>
                </div>
                <div className="rounded-[2px] border border-sand-200 p-3">
                  <dt className="eyebrow">Verilmiş hak</dt>
                  <dd className="mt-1 display text-2xl tabular-nums">{c.grantCount}</dd>
                  <dd className="muted">öncelik: {c.priority}</dd>
                </div>
              </dl>
            </article>
          );
        })}
      </div>
    </div>
  );
}
