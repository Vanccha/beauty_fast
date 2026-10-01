'use client';

import { useEffect, useState } from 'react';

import { isStandalone, promptInstall, useCanInstall, useIsIosSafari } from './install';

const DISMISS_KEY = 'aurora:install-dismissed-at';
const DISMISS_DAYS = 30;

function recentlyDismissed(): boolean {
  try {
    const at = Number(localStorage.getItem(DISMISS_KEY));
    return Number.isFinite(at) && Date.now() - at < DISMISS_DAYS * 86_400_000;
  } catch {
    return false;
  }
}

/**
 * Müşteri arayüzünde "uygulamayı ana ekrana ekle" önerisi.
 *
 * Mobilde alt gezinme çubuğunun hemen üstünde, `md:` üstünde sağ alt
 * köşede kart olarak görünür. Kapatılırsa 30 gün boyunca gösterilmez.
 * Zaten yüklü (bağımsız pencerede) açıldıysa hiç görünmez.
 */
export function InstallBanner({ appName }: { appName: string }) {
  const canInstall = useCanInstall();
  const ios = useIsIosSafari();
  const [eligible, setEligible] = useState(false);

  useEffect(() => {
    if (isStandalone() || recentlyDismissed()) return;
    // Açılışta hemen araya girmesin; ziyaretçi önce sayfayı görsün.
    const t = window.setTimeout(() => setEligible(true), 3000);
    return () => window.clearTimeout(t);
  }, []);

  if (!eligible || !(canInstall || ios)) return null;

  const dismiss = () => {
    try {
      localStorage.setItem(DISMISS_KEY, String(Date.now()));
    } catch {
      /* gizli sekme vb. — yalnızca bu oturumda gizle */
    }
    setEligible(false);
  };

  return (
    <div
      role="dialog"
      aria-label="Uygulamayı yükle"
      className="fixed inset-x-3 z-30 bottom-[calc(4.5rem+env(safe-area-inset-bottom))] md:inset-x-auto md:bottom-6 md:right-6 md:w-96"
    >
      <div className="card flex items-start gap-3 shadow-lg">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/icons/icon-192.png" alt="" width={44} height={44} className="shrink-0 rounded-xl" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{appName} uygulaması</p>
          {canInstall ? (
            <p className="muted mt-0.5">Ana ekrana ekle, randevunu tek dokunuşla al.</p>
          ) : (
            <p className="muted mt-0.5">
              Safari&apos;de <span aria-hidden>⎋</span>
              <strong className="font-semibold"> Paylaş</strong> düğmesine, ardından{' '}
              <strong className="font-semibold">Ana Ekrana Ekle</strong>&apos;ye dokun.
            </p>
          )}
          <div className="mt-3 flex gap-2">
            {canInstall && (
              <button
                type="button"
                className="btn-primary py-2"
                onClick={async () => {
                  if (await promptInstall()) setEligible(false);
                }}
              >
                Yükle
              </button>
            )}
            <button type="button" className="btn-ghost py-2" onClick={dismiss}>
              {canInstall ? 'Şimdi değil' : 'Tamam'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Personel paneli: yalnızca tarayıcı yüklemeye izin verdiğinde görünen düğme. */
export function InstallButton() {
  const canInstall = useCanInstall();
  if (!canInstall) return null;
  return (
    <button type="button" className="btn-ghost hidden text-sm sm:inline-flex" onClick={() => promptInstall()}>
      Uygulamayı yükle
    </button>
  );
}
