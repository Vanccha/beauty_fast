'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, apiGet, apiSend } from '@/lib/api-client';

export interface MessagingStatus {
  driver: string;
  ready: boolean;
  /** open | connecting | close | missing | unreachable | console */
  state: string;
  error?: string;
}

interface QrResponse {
  state: string;
  qr: string | null;
  pairingCode: string | null;
}

const STATE_LABELS: Record<string, { label: string; tone: string }> = {
  open: { label: 'Bağlı', tone: 'border border-emerald-300 bg-transparent text-emerald-700' },
  connecting: { label: 'Bağlanmayı bekliyor', tone: 'border border-brass-300 bg-transparent text-brass-700' },
  close: { label: 'Bağlı değil', tone: 'border border-rose-300 bg-transparent text-rose-700' },
  missing: { label: 'Henüz kurulmadı', tone: 'border border-sand-200 bg-sand-100 text-ink-700' },
  unreachable: { label: 'Geçide ulaşılamıyor', tone: 'border border-rose-300 bg-transparent text-rose-700' },
};

/** QR kodu ~40 sn geçerlidir; süresi dolmadan yenisi istenir. */
const QR_REFRESH_MS = 30_000;
/** Bu kadar yenilemeden sonra otomatik yenileme durur (boşta QR üretmesin). */
const MAX_QR_REFRESHES = 6;
const POLL_WHILE_QR_MS = 3_000;
const POLL_IDLE_MS = 15_000;

export function WhatsappConnect({
  initialStatus,
  canManage,
}: {
  initialStatus: MessagingStatus;
  canManage: boolean;
}) {
  const [status, setStatus] = useState(initialStatus);
  const [qr, setQr] = useState<QrResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const refreshes = useRef(0);

  const refreshStatus = useCallback(async () => {
    try {
      const next = await apiGet<MessagingStatus>('/api/admin/messaging/status');
      setStatus(next);
      return next;
    } catch {
      return null;
    }
  }, []);

  const requestQr = useCallback(async () => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await apiSend<QrResponse>('/api/admin/messaging/qr', 'POST');
      if (!result.qr) {
        setQr(null);
        setNotice('Numara zaten bağlı.');
        await refreshStatus();
      } else {
        setQr(result);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'QR kodu alınamadı.');
      setQr(null);
    } finally {
      setBusy(false);
    }
  }, [refreshStatus]);

  // Durum takibi: QR ekrandayken sık, değilken seyrek.
  useEffect(() => {
    if (status.driver !== 'evolution') return;
    const timer = setInterval(async () => {
      const next = await refreshStatus();
      if (qr && next?.state === 'open') {
        setQr(null);
        setNotice('Bağlantı kuruldu. Mesajlar artık bu numaradan gönderilecek.');
      }
    }, qr ? POLL_WHILE_QR_MS : POLL_IDLE_MS);
    return () => clearInterval(timer);
  }, [qr, status.driver, refreshStatus]);

  // QR süresi dolmadan yenile; belirli bir sayıdan sonra dur.
  useEffect(() => {
    if (!qr) {
      refreshes.current = 0;
      return;
    }
    const timer = setTimeout(() => {
      if (refreshes.current >= MAX_QR_REFRESHES) {
        setQr(null);
        setNotice('QR kodunun süresi doldu. Hazır olduğunuzda yeniden oluşturun.');
        return;
      }
      refreshes.current += 1;
      void requestQr();
    }, QR_REFRESH_MS);
    return () => clearTimeout(timer);
  }, [qr, requestQr]);

  async function logout() {
    if (
      !window.confirm(
        'WhatsApp bağlantısı kesilsin mi? Yeniden QR okutulana kadar müşteriler giriş kodu alamaz ve hatırlatmalar gitmez.',
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await apiSend('/api/admin/messaging/logout', 'POST');
      await refreshStatus();
      setNotice('Bağlantı kesildi.');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Bağlantı kesilemedi.');
    } finally {
      setBusy(false);
    }
  }

  if (status.driver !== 'evolution') {
    return (
      <section className="card space-y-1 !p-4">
        <p className="eyebrow">WhatsApp gönderimi kapalı</p>
        <p className="muted">
          Sunucu şu an mesajları yalnızca log&apos;a yazıyor (geliştirme modu). WhatsApp&apos;ı açmak
          için sunucu ayarlarında <code>NOTIFICATION_DRIVER=evolution</code> ve Evolution API
          bilgileri tanımlanmalı.
        </p>
      </section>
    );
  }

  const badge = STATE_LABELS[status.state] ?? {
    label: status.state,
    tone: 'border border-sand-200 bg-sand-100 text-ink-700',
  };
  const connected = status.state === 'open';

  return (
    <section className="card space-y-3 !p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="eyebrow">Durum</span>
          <span className={`badge ${badge.tone}`} aria-live="polite">
            {badge.label}
          </span>
        </div>

        {canManage && (
          <div className="flex flex-wrap gap-2">
            {!connected && (
              <button type="button" className="btn-primary btn-sm" disabled={busy} onClick={requestQr}>
                {qr ? 'QR kodunu yenile' : 'QR kodu ile bağla'}
              </button>
            )}
            {connected && (
              <button type="button" className="btn-secondary btn-sm" disabled={busy} onClick={logout}>
                Bağlantıyı kes
              </button>
            )}
          </div>
        )}
      </div>

      {status.state === 'unreachable' && (
        <p className="rounded-[2px] border border-rose-300 px-3 py-2 text-sm text-rose-700">
          WhatsApp geçidine (Evolution API) ulaşılamıyor. Sunucuda Evolution API&apos;nin çalıştığından
          emin olun.
        </p>
      )}

      {!canManage && !connected && (
        <p className="muted">Numarayı yalnızca salon sahibi bağlayabilir.</p>
      )}

      {qr?.qr && (
        <div className="grid gap-4 md:grid-cols-[auto,1fr] md:items-center">
          {/* data URL olduğu için next/image yerine düz img */}
          <img
            src={qr.qr}
            alt="WhatsApp bağlantı QR kodu"
            width={264}
            height={264}
            className="mx-auto rounded-[4px] border border-sand-200 bg-white p-2"
          />
          <div className="space-y-2 text-sm">
            <p className="eyebrow">Telefonda şu adımları izleyin</p>
            <ol className="list-decimal space-y-1 pl-5 text-ink-700">
              <li>Bu salon için kullanılacak telefonda WhatsApp&apos;ı açın.</li>
              <li>
                <strong>Ayarlar › Bağlı cihazlar › Cihaz bağla</strong> adımlarına gidin.
              </li>
              <li>Ekrandaki QR kodunu okutun.</li>
            </ol>
            {qr.pairingCode && (
              <p>
                QR okutamıyorsanız eşleştirme kodu: <strong>{qr.pairingCode}</strong>
              </p>
            )}
            <p className="muted">
              Kod birkaç saniyede bir kontrol edilir ve süresi dolmadan kendiliğinden yenilenir.
              Bağlantı kurulunca bu alan kapanır.
            </p>
          </div>
        </div>
      )}

      {notice && <p className="text-sm text-emerald-700">{notice}</p>}
      {error && <p className="text-sm text-danger-700">{error}</p>}
    </section>
  );
}
