'use client';

import { useEffect } from 'react';

/**
 * Service worker kaydı (`public/sw.js`).
 *
 * Yalnızca üretim derlemesinde kaydedilir: `next dev` altında bir SW
 * eski JS parçalarını önbellekten sunup sıcak yenilemeyi bozar. Geliştirme
 * sırasında daha önce kaydedilmiş bir SW kalmışsa kaldırılır.
 */
export function ServiceWorkerRegister() {
  useEffect(() => {
    if (!('serviceWorker' in navigator)) return;

    if (process.env.NODE_ENV !== 'production') {
      navigator.serviceWorker
        .getRegistrations()
        .then((regs) => regs.forEach((r) => r.unregister()))
        .catch(() => undefined);
      return;
    }

    const register = () => {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => undefined);
    };
    // İlk boyamayla yarışmasın: sayfa yüklendikten sonra kaydet.
    if (document.readyState === 'complete') register();
    else {
      window.addEventListener('load', register, { once: true });
      return () => window.removeEventListener('load', register);
    }
  }, []);

  return null;
}
