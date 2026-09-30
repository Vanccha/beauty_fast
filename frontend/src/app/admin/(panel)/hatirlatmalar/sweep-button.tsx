'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { apiSend } from '@/lib/api-client';

/**
 * Bakım işini elle tetikler (`/api/cron/sweep`): süresi dolmuş kilitleri
 * ve oturumları siler, zamanı gelen bildirimleri "gönderir".
 *
 * Lokal projede zamanlayıcı servisi yoktur; doğruluk buna bağlı değildir
 * (kilitler her `acquireSlotLock` çağrısında da temizlenir), bu düğme
 * yalnızca gözlemlenebilirlik ve tablo temizliği içindir.
 */
export function SweepButton({ pendingDue }: { pendingDue: number }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);

  return (
    <div className="text-right">
      <button
        type="button"
        className="btn-primary"
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          try {
            const data = await apiSend<{
              removedLocks: number;
              removedCodes: number;
              notificationsSent: number;
            }>('/api/cron/sweep', 'POST');
            setResult(
              `${data.notificationsSent} bildirim gönderildi · ${data.removedLocks} kilit, ${data.removedCodes} kod temizlendi`,
            );
            router.refresh();
          } catch {
            setResult('Bakım işi başarısız.');
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? 'İşleniyor…' : `Kuyruğu işle${pendingDue ? ` (${pendingDue})` : ''}`}
      </button>
      {result && <p className="mt-1 text-xs text-ink-500">{result}</p>}
    </div>
  );
}
