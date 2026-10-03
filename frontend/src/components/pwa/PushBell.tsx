'use client';

import { Bell, BellOff, BellRing, Smartphone } from 'lucide-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError, apiGet, apiSend } from '@/lib/api-client';

import { isStandalone, useIsIosSafari } from './install';

interface Prefs {
  newAppointment: boolean;
  cancelled: boolean;
  alerts: boolean;
  whatsapp: boolean;
  deposit: boolean;
}

interface PublicKey {
  enabled: boolean;
  publicKey: string;
  canManage: boolean;
}

interface SubscriptionState {
  subscribed: boolean;
  prefs: Prefs | null;
}

type Status =
  | 'loading'
  | 'unsupported' // tarayıcı Web Push bilmiyor
  | 'ios-install' // iPhone: önce ana ekrana eklenmeli
  | 'server-off' // sunucuda VAPID anahtarı yok
  | 'denied' // izin reddedilmiş
  | 'off' // bu cihazda kapalı
  | 'on'; // bu cihazda açık

const EVENTS: { key: keyof Prefs; label: string; managerOnly?: boolean }[] = [
  { key: 'newAppointment', label: 'Yeni randevu' },
  { key: 'cancelled', label: 'İptal' },
  { key: 'alerts', label: 'Uyarılar (düşük puan, kritik stok)', managerOnly: true },
  { key: 'whatsapp', label: 'WhatsApp bağlantısı', managerOnly: true },
  { key: 'deposit', label: 'Kapora (bekleyen, iade)', managerOnly: true },
];

function urlBase64ToUint8Array(base64: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4);
  const raw = atob((base64 + padding).replace(/-/g, '+').replace(/_/g, '/'));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

function browserSupportsPush(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

/** Kayıtlı SW'yi (yoksa üretimde bekleyerek, geliştirmede önbelleksiz kopyayı kaydederek) döner. */
async function getRegistration(create: boolean): Promise<ServiceWorkerRegistration | undefined> {
  if (!create) return navigator.serviceWorker.getRegistration();
  if (process.env.NODE_ENV !== 'production') {
    await navigator.serviceWorker.register('/sw.js?push-only=1', { scope: '/' });
  }
  return navigator.serviceWorker.ready;
}

/**
 * Admin üst barı: zil düğmesi + "Bildirimler" paneli.
 *
 * İzin YALNIZCA "Bu cihazda bildirimleri aç" düğmesine basılınca istenir.
 * Abonelik cihaz başınadır; tercihler (hangi olaylar) her cihaz için ayrıdır.
 */
export function PushBell() {
  const ios = useIsIosSafari();
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<Status>('loading');
  const [prefs, setPrefs] = useState<Prefs | null>(null);
  const [canManage, setCanManage] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  const refresh = useCallback(async () => {
    if (!browserSupportsPush()) {
      setStatus(ios && !isStandalone() ? 'ios-install' : 'unsupported');
      return;
    }
    try {
      const key = await apiGet<PublicKey>('/api/admin/push/public-key');
      setCanManage(key.canManage);
      if (!key.enabled) return setStatus('server-off');
      if (Notification.permission === 'denied') return setStatus('denied');

      const reg = await getRegistration(false);
      const sub = await reg?.pushManager.getSubscription();
      if (!sub || Notification.permission !== 'granted') {
        setPrefs(null);
        return setStatus('off');
      }
      const state = await apiGet<SubscriptionState>(
        `/api/admin/push/subscription?endpoint=${encodeURIComponent(sub.endpoint)}`,
      );
      setPrefs(state.prefs);
      setStatus(state.subscribed ? 'on' : 'off');
    } catch {
      setStatus('off');
    }
  }, [ios]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setMessage(null);
    try {
      await fn();
    } catch (e) {
      setMessage({
        tone: 'error',
        text: e instanceof ApiError || e instanceof Error ? e.message : 'İşlem tamamlanamadı.',
      });
    } finally {
      setBusy(false);
    }
  };

  const enable = () =>
    run(async () => {
      // İzin yalnızca bu tıklamada istenir.
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setStatus(permission === 'denied' ? 'denied' : 'off');
        return;
      }
      const key = await apiGet<PublicKey>('/api/admin/push/public-key');
      if (!key.enabled) return setStatus('server-off');
      const reg = await getRegistration(true);
      if (!reg) throw new Error('Servis çalışanı hazır değil.');
      const applicationServerKey = urlBase64ToUint8Array(key.publicKey);
      let sub = await reg.pushManager.getSubscription();
      if (!sub) {
        sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey });
      }
      const json = sub.toJSON();
      const state = await apiSend<SubscriptionState>('/api/admin/push/subscribe', 'POST', {
        endpoint: json.endpoint,
        keys: json.keys,
      });
      setPrefs(state.prefs);
      setStatus('on');
      setMessage({ tone: 'ok', text: 'Bildirimler bu cihazda açıldı.' });
    });

  const disable = () =>
    run(async () => {
      const reg = await getRegistration(false);
      const sub = await reg?.pushManager.getSubscription();
      if (sub) {
        await apiSend('/api/admin/push/subscribe', 'DELETE', { endpoint: sub.endpoint });
        await sub.unsubscribe();
      }
      setPrefs(null);
      setStatus('off');
    });

  const toggle = (key: keyof Prefs) =>
    run(async () => {
      if (!prefs) return;
      const reg = await getRegistration(false);
      const sub = await reg?.pushManager.getSubscription();
      if (!sub) return;
      const next = { ...prefs, [key]: !prefs[key] };
      setPrefs(next); // iyimser güncelleme
      try {
        const state = await apiSend<SubscriptionState>('/api/admin/push/prefs', 'PUT', {
          endpoint: sub.endpoint,
          [key]: next[key],
        });
        setPrefs(state.prefs);
      } catch (e) {
        setPrefs(prefs);
        throw e;
      }
    });

  const sendTest = () =>
    run(async () => {
      const res = await apiSend<{ sent: number; failed: number; removed: number }>(
        '/api/admin/push/test',
        'POST',
      );
      setMessage(
        res.sent > 0
          ? { tone: 'ok', text: 'Test bildirimi gönderildi.' }
          : { tone: 'error', text: 'Bildirim gönderilemedi. Bildirimleri kapatıp yeniden açın.' },
      );
      if (res.removed > 0) await refresh();
    });

  const Icon = status === 'on' ? BellRing : status === 'denied' || status === 'unsupported' ? BellOff : Bell;

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        onClick={() => {
          setOpen((o) => !o);
          if (!open) void refresh();
        }}
        aria-label="Bildirimler"
        aria-expanded={open}
        className="touch-target relative inline-flex items-center justify-center rounded-full px-2.5 text-ink-700 transition-colors hover:bg-plum-50 hover:text-plum-600"
      >
        <Icon size={18} strokeWidth={1.5} aria-hidden />
        {status === 'on' && (
          <span className="absolute right-2 top-2 size-2 rounded-full bg-plum-600" aria-hidden />
        )}
      </button>

      {open && (
        <div
          role="dialog"
          aria-label="Bildirimler"
          className="card absolute right-0 top-full z-40 mt-2 w-[min(22rem,calc(100vw-1.5rem))] !p-5 text-ink-900 shadow-[0_12px_32px_-12px_rgb(34_30_27/0.18)]"
        >
          <p className="eyebrow">Bildirimler</p>
          <p className="display mt-1 text-lg leading-tight">Bu cihazda anlık bildirim</p>

          <p className="muted mt-2" aria-live="polite">
            {status === 'loading' && 'Kontrol ediliyor…'}
            {status === 'unsupported' && 'Bu tarayıcı bildirimleri desteklemiyor.'}
            {status === 'server-off' && 'Sunucuda bildirimler kapalı (VAPID anahtarı tanımlı değil).'}
            {status === 'denied' && 'İzin verilmedi.'}
            {status === 'off' && 'Kapalı.'}
            {status === 'on' && 'Açık: bu cihaz bildirim alıyor.'}
          </p>

          {status === 'ios-install' && (
            <p className="mt-3 flex items-start gap-2.5 text-sm text-ink-700">
              <Smartphone size={16} strokeWidth={1.5} className="mt-0.5 shrink-0 text-plum-700" aria-hidden />
              <span>
                iPhone&apos;da bildirim için önce &apos;Ana Ekrana Ekle&apos; ile uygulamayı yükleyin, sonra uygulamayı
                ana ekrandan açıp bildirimleri etkinleştirin.
              </span>
            </p>
          )}

          {status === 'denied' && (
            <p className="mt-2 text-sm text-ink-700">
              Tarayıcı bu site için bildirimleri engelliyor. Adres çubuğundaki kilit simgesinden (iPhone&apos;da
              Ayarlar &rsaquo; Bildirimler) izni &quot;İzin ver&quot; yapıp sayfayı yenileyin.
            </p>
          )}

          {status === 'off' && (
            <button type="button" className="btn-primary btn-sm mt-3 w-full" onClick={enable} disabled={busy}>
              Bu cihazda bildirimleri aç
            </button>
          )}

          {status === 'on' && prefs && (
            <>
              <ul className="mt-3 divide-y divide-sand-200 border-y border-sand-200">
                {EVENTS.filter((ev) => !ev.managerOnly || canManage).map((ev) => (
                  <li key={ev.key}>
                    <label className="flex min-h-11 cursor-pointer items-center justify-between gap-3 py-2 text-sm">
                      <span>{ev.label}</span>
                      <input
                        type="checkbox"
                        role="switch"
                        className="size-5 shrink-0 accent-plum-600"
                        checked={prefs[ev.key]}
                        disabled={busy}
                        onChange={() => toggle(ev.key)}
                      />
                    </label>
                  </li>
                ))}
              </ul>
              <div className="mt-3 flex gap-2">
                <button type="button" className="btn-secondary btn-sm flex-1" onClick={sendTest} disabled={busy}>
                  Test bildirimi gönder
                </button>
                <button type="button" className="btn-ghost btn-sm" onClick={disable} disabled={busy}>
                  Kapat
                </button>
              </div>
            </>
          )}

          {message && (
            <p
              role="status"
              className={`mt-3 text-sm ${message.tone === 'error' ? 'text-danger-600' : 'text-ink-700'}`}
            >
              {message.text}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
