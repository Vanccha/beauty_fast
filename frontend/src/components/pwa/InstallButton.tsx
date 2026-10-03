'use client';

import { Download, Share } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { isStandalone, promptInstall, useCanInstall, useIsIosSafari } from './install';

/** Uygulama zaten ana ekrandan açıldıysa true. İlk boyamada false (sunucuyla aynı). */
function useIsStandalone(): boolean {
  const [standalone, setStandalone] = useState(false);
  useEffect(() => setStandalone(isStandalone()), []);
  return standalone;
}

/**
 * Müşteri üst barı: sabit "Uygulamayı yükle" düğmesi.
 *
 * - Android / Chrome / Edge / Samsung: tarayıcının yükleme penceresini açar.
 * - iOS / iPadOS Safari: otomatik pencere olmadığı için düğmenin altında
 *   "Paylaş → Ana Ekrana Ekle" adımlarını gösteren küçük bir kutu açar.
 * - Yükleme mümkün değilse veya uygulama zaten ana ekrandan açıldıysa
 *   hiç görünmez.
 *
 * Mobilde yalnızca simge, `md:` üstünde simge + yazı.
 */
export function SiteInstallButton({ transparent }: { transparent: boolean }) {
  const canInstall = useCanInstall();
  const ios = useIsIosSafari();
  const standalone = useIsStandalone();
  const [helpOpen, setHelpOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!helpOpen) return;
    const onDown = (e: PointerEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setHelpOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setHelpOpen(false);
    document.addEventListener('pointerdown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [helpOpen]);

  if (standalone || !(canInstall || ios)) return null;

  const onClick = () => {
    if (canInstall) void promptInstall();
    else setHelpOpen((o) => !o);
  };

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        onClick={onClick}
        aria-label="Uygulamayı yükle"
        aria-expanded={canInstall ? undefined : helpOpen}
        className={`touch-target inline-flex items-center justify-center gap-2 rounded-full px-2.5 text-xs font-semibold uppercase tracking-[0.14em] transition-colors md:px-3 ${
          transparent ? 'text-white hover:bg-white/15' : 'text-ink-700 hover:bg-plum-50 hover:text-plum-600'
        }`}
      >
        <Download size={18} strokeWidth={1.5} aria-hidden />
        <span className="hidden whitespace-nowrap xl:inline">Uygulamayı yükle</span>
      </button>

      {helpOpen && (
        <div
          role="dialog"
          aria-label="Ana ekrana ekleme"
          className="card absolute right-0 top-full z-40 mt-2 w-72 !p-5 text-ink-900 shadow-[0_12px_32px_-12px_rgb(34_30_27/0.18)]"
        >
          <div className="flex items-start gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/icons/icon-192.png" alt="" width={40} height={40} className="shrink-0 rounded-[2px]" />
            <p className="muted">
              Safari&apos;de <Share size={14} strokeWidth={1.5} aria-hidden className="inline align-[-2px]" />
              <strong className="font-semibold"> Paylaş</strong> düğmesine, ardından{' '}
              <strong className="font-semibold">Ana Ekrana Ekle</strong>&apos;ye dokun.
            </p>
          </div>
          <button type="button" className="btn-ghost btn-sm mt-3 w-full" onClick={() => setHelpOpen(false)}>
            Tamam
          </button>
        </div>
      )}
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
