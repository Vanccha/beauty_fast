'use client';

import { useEffect } from 'react';

/** Bağlantı geri geldiğinde sayfayı kendiliğinden yeniler. */
export function RetryButton() {
  useEffect(() => {
    const onOnline = () => window.location.reload();
    window.addEventListener('online', onOnline);
    return () => window.removeEventListener('online', onOnline);
  }, []);

  return (
    <button type="button" className="btn-primary mt-6 w-full" onClick={() => window.location.reload()}>
      Tekrar dene
    </button>
  );
}
