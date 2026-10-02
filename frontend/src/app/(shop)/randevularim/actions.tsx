'use client';

import { useRouter } from 'next/navigation';
import { LogOut, TriangleAlert } from 'lucide-react';
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
    <div className="mt-4 border-t border-sand-200 pt-4">
      {error && (
        <div className="alert alert-danger mb-3" role="alert">
          <TriangleAlert size={16} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
          <p>{error}</p>
        </div>
      )}

      {confirming ? (
        <div className="flex gap-2">
          <button type="button" className="btn-secondary btn-sm flex-1" onClick={() => setConfirming(false)}>
            Vazgeç
          </button>
          <button
            type="button"
            className="btn-danger btn-sm flex-1"
            disabled={busy}
            onClick={() => void cancel()}
          >
            {busy ? 'İptal ediliyor…' : 'Evet, iptal et'}
          </button>
        </div>
      ) : (
        <button type="button" className="btn-link text-danger-600 hover:text-danger-700" onClick={() => setConfirming(true)}>
          Randevuyu iptal et
        </button>
      )}
    </div>
  );
}

/** Grup randevusunun tamamını iptal eder (yalnızca rezervasyonu yapan kişi). */
export function GroupCancel({ groupId }: { groupId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  async function cancel() {
    setBusy(true);
    setError(null);
    try {
      await apiSend(`/api/appointments/group/${encodeURIComponent(groupId)}/cancel`, 'POST');
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Grup iptal edilemedi.');
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  }

  return (
    <div>
      {error && (
        <div className="alert alert-danger mb-3" role="alert">
          <TriangleAlert size={16} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
          <p>{error}</p>
        </div>
      )}
      {confirming ? (
        <div className="flex gap-2">
          <button type="button" className="btn-secondary btn-sm" onClick={() => setConfirming(false)}>
            Vazgeç
          </button>
          <button type="button" className="btn-danger btn-sm" disabled={busy} onClick={() => void cancel()}>
            {busy ? 'İptal ediliyor…' : 'Evet, grubun tamamını iptal et'}
          </button>
        </div>
      ) : (
        <button
          type="button"
          className="btn-link text-danger-600 hover:text-danger-700"
          onClick={() => setConfirming(true)}
        >
          Grubu iptal et
        </button>
      )}
    </div>
  );
}

/** Oturumu bu cihazdan kapatır. */
export function LogoutButton() {
  const router = useRouter();
  return (
    <button
      type="button"
      className="btn-link text-ink-500"
      onClick={async () => {
        await apiSend('/api/auth/logout', 'POST', { scope: 'customer' }).catch(() => undefined);
        router.push('/');
        router.refresh();
      }}
    >
      <LogOut size={14} strokeWidth={1.5} aria-hidden />
      Bu cihazdan çık
    </button>
  );
}
