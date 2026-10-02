'use client';

import { RefreshCw } from 'lucide-react';
import { useEffect } from 'react';

/** Bağlantı geri geldiğinde sayfayı kendiliğinden yeniler. */
export function RetryButton() {
  useEffect(() => {
    const onOnline = () => window.location.reload();
    window.addEventListener('online', onOnline);
    return () => window.removeEventListener('online', onOnline);
  }, []);

  return (
    <button type="button" className="btn-primary mt-8 w-full" onClick={() => window.location.reload()}>
      <RefreshCw size={16} strokeWidth={1.5} aria-hidden />
      Tekrar dene
    </button>
  );
}
