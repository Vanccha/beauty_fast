'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { apiSend } from '@/lib/api-client';

/** Kampanyayı yayına alır/durdurur. Yalnızca MANAGER ve üzeri yetkilidir. */
export function CampaignToggle({ id, isActive }: { id: number; isActive: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <>
      <button
        type="button"
        className={isActive ? 'btn-secondary btn-sm' : 'btn-primary btn-sm'}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError(null);
          try {
            await apiSend('/api/admin/campaigns', 'PATCH', { id, isActive: !isActive });
            router.refresh();
          } catch {
            setError('Yetkiniz yok veya güncelleme başarısız.');
          } finally {
            setBusy(false);
          }
        }}
      >
        {isActive ? 'Durdur' : 'Yayınla'}
      </button>
      {error && <span className="text-xs text-danger-700">{error}</span>}
    </>
  );
}
