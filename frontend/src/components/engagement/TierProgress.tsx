import { Award, Crown } from 'lucide-react';

/** Seviye kodu -> etiket ve rozet tonu. Bilinmeyen kod Bronz gibi gösterilir. */
const TIERS: Record<string, { label: string; tone: string; icon: typeof Award }> = {
  BRONZ: { label: 'Bronz', tone: 'border-brass-300 bg-[#f6ece0] text-brass-700', icon: Award },
  GUMUS: { label: 'Gümüş', tone: 'border-sand-300 bg-sand-100 text-ink-700', icon: Award },
  ALTIN: { label: 'Altın', tone: 'border-brass-500/60 bg-[#f5e9c8] text-brass-700', icon: Award },
  VIP: { label: 'VIP', tone: 'border-plum-300 bg-plum-50 text-plum-700', icon: Crown },
};

/**
 * Sadakat seviyesi: küçük bir rozet + ince ilerleme çubuğu.
 *
 * Gösterilen "kalan puan" gerçek `LoyaltyEntry` defterinden türetilen
 * bakiyeden hesaplanır (`progressToNextTier`), tahmin veya yuvarlama
 * yapılmaz. `optIn` kapalıysa bileşen hiç render edilmez.
 */
export function TierProgress({
  points,
  progress,
  optIn = true,
}: {
  points: number;
  progress: { current: string; next: string | null; pointsToNext: number; ratio: number; message: string };
  optIn?: boolean;
}) {
  if (!optIn) return null;

  const tier = TIERS[progress.current] ?? TIERS.BRONZ;
  const Icon = tier.icon;

  return (
    <div className="rounded-2xl border border-sand-200 bg-white px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <span
          className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold ${tier.tone}`}
          title="Sadakat seviyen"
        >
          <Icon size={14} strokeWidth={1.75} aria-hidden />
          {tier.label} üye
        </span>
        <span className="text-sm text-ink-500">
          <span className="font-semibold tabular-nums text-ink-900">{Math.round(points)}</span> puan
        </span>
      </div>

      <div
        className="mt-3 h-1 w-full overflow-hidden rounded-full bg-sand-100"
        role="progressbar"
        aria-valuenow={Math.round(progress.ratio * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Sonraki seviyeye ilerleme"
      >
        <div
          className="h-full rounded-full bg-plum-500 transition-[width] duration-500"
          style={{ width: `${Math.round(progress.ratio * 100)}%` }}
        />
      </div>

      <p className="mt-1.5 text-xs text-ink-500">{progress.message}</p>
    </div>
  );
}
