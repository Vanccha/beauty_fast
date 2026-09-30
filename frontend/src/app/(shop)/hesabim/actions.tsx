'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ApiError, apiSend } from '@/lib/api-client';

/**
 * Randevu iptali.
 *
 * `expectedVersion` gönderilir: sayfa açıkken salon randevuyu
 * güncellediyse (örn. taşıdıysa) iptal `VERSION_MISMATCH` ile reddedilir
 * ve kullanıcıdan sayfayı yenilemesi istenir — eski veriyle karar
 * verilmesi engellenir.
 */
export function AppointmentActions({
  appointmentId,
  version,
}: {
  appointmentId: number;
  version: number;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  async function cancel() {
    setBusy(true);
    setError(null);
    try {
      await apiSend(`/api/appointments/${appointmentId}`, 'PATCH', {
        status: 'CANCELLED',
        expectedVersion: version,
      });
      router.refresh();
    } catch (e) {
      setError(
        e instanceof ApiError && e.code === 'VERSION_MISMATCH'
          ? 'Bu randevu salon tarafından güncellendi. Lütfen sayfayı yenileyin.'
          : e instanceof ApiError
            ? e.message
            : 'İptal edilemedi.',
      );
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <div className="mt-3 border-t border-sand-100 pt-3">
      {error && <p className="mb-2 text-sm text-rose-600">{error}</p>}

      {confirming ? (
        <div className="flex gap-2">
          <button type="button" className="btn-secondary flex-1" onClick={() => setConfirming(false)}>
            Vazgeç
          </button>
          <button
            type="button"
            className="btn flex-1 bg-rose-600 text-white hover:bg-rose-700"
            disabled={busy}
            onClick={() => void cancel()}
          >
            {busy ? 'İptal ediliyor…' : 'Evet, iptal et'}
          </button>
        </div>
      ) : (
        <button type="button" className="btn-ghost text-rose-600" onClick={() => setConfirming(true)}>
          Randevuyu iptal et
        </button>
      )}
    </div>
  );
}

export function LogoutButton() {
  const router = useRouter();
  return (
    <button
      type="button"
      className="btn-ghost text-sm"
      onClick={async () => {
        await apiSend('/api/auth/logout', 'POST', { scope: 'customer' }).catch(() => undefined);
        router.push('/');
        router.refresh();
      }}
    >
      Çıkış
    </button>
  );
}
