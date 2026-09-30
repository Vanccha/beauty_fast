import { formatTl } from '@/lib/api-client';

/**
 * Sadakat seviyesi ilerleme çubuğu.
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

  return (
    <div className="card">
      <div className="flex items-baseline justify-between">
        <div>
          <p className="muted">Sadakat seviyesi</p>
          <p className="text-xl font-semibold text-plum-700">{progress.current}</p>
        </div>
        <div className="text-right">
          <p className="text-xl font-semibold tabular-nums">{Math.round(points)}</p>
          <p className="muted">puan ≈ {formatTl(points * 0.1)}</p>
        </div>
      </div>

      <div
        className="mt-3 h-2.5 w-full overflow-hidden rounded-full bg-sand-200"
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

      <p className="mt-2 muted">{progress.message}</p>
    </div>
  );
}
