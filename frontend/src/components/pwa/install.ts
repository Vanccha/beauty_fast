'use client';

import { useEffect, useState, useSyncExternalStore } from 'react';

/**
 * "Ana ekrana ekle" durumunun ortak kaynağı.
 *
 * `beforeinstallprompt` sayfa yüklenir yüklenmez — çoğu zaman React
 * hidrasyonundan ÖNCE — tetiklenebilir. Bu yüzden dinleyici modül
 * değerlendirilirken kurulur ve olay burada saklanır; bileşenler
 * sonradan abone olur.
 */
interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }>;
}

let deferred: BeforeInstallPromptEvent | null = null;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

if (typeof window !== 'undefined') {
  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault(); // Tarayıcının kendi mini çubuğu yerine bizimkini göster.
    deferred = e as BeforeInstallPromptEvent;
    notify();
  });
  window.addEventListener('appinstalled', () => {
    deferred = null;
    notify();
  });
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

/** Tarayıcı yükleme penceresi açılabiliyorsa true (Chrome/Edge/Samsung). */
export function useCanInstall(): boolean {
  return useSyncExternalStore(
    subscribe,
    () => deferred !== null,
    () => false,
  );
}

/** Yükleme penceresini açar; kullanıcı kabul ettiyse true döner. */
export async function promptInstall(): Promise<boolean> {
  if (!deferred) return false;
  const event = deferred;
  deferred = null;
  notify();
  await event.prompt();
  const { outcome } = await event.userChoice;
  return outcome === 'accepted';
}

/** Uygulama zaten ana ekrandan (bağımsız pencerede) mi açıldı? */
export function isStandalone(): boolean {
  return (
    window.matchMedia('(display-mode: standalone)').matches ||
    // iOS Safari
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

/**
 * iOS/iPadOS Safari: `beforeinstallprompt` desteklenmez, kullanıcıya
 * "Paylaş → Ana Ekrana Ekle" yolu tarif edilmelidir. iPadOS 13+ kendini
 * masaüstü Safari olarak tanıttığından dokunmatik nokta sayısına bakılır.
 */
export function useIsIosSafari(): boolean {
  const [ios, setIos] = useState(false);
  useEffect(() => {
    const ua = navigator.userAgent;
    const iDevice =
      /iPad|iPhone|iPod/.test(ua) || (ua.includes('Macintosh') && navigator.maxTouchPoints > 1);
    // iOS'taki diğer tarayıcılar (CriOS, FxiOS, EdgiOS) ana ekrana eklemeyi Safari'ye bırakır.
    const safari = !/CriOS|FxiOS|EdgiOS|OPiOS/.test(ua);
    setIos(iDevice && safari);
  }, []);
  return ios;
}
