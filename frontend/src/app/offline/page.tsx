import type { Metadata } from 'next';

import { RetryButton } from './retry-button';

export const metadata: Metadata = { title: 'Çevrimdışı — Aurora Beauty Studio' };

/**
 * Çevrimdışı yedek sayfası.
 *
 * Service worker kurulumda bu sayfayı önbelleğe alır ve ağ yokken
 * açılmak istenen herhangi bir sayfa yerine bunu gösterir.
 *
 * BİLEREK `(shop)` grubunun DIŞINDA: o kabuk her istekte API'den salon
 * bilgisi çeker; burada hiçbir veri çağrısı olmamalı ki sayfa statik
 * üretilsin ve önbellekten tek başına açılabilsin.
 */
export default function OfflinePage() {
  return (
    <main className="grid min-h-dvh place-items-center px-6 py-[max(2rem,env(safe-area-inset-top))] text-center">
      <div className="max-w-sm">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/icons/icon-192.png" alt="" width={72} height={72} className="mx-auto rounded-2xl" />
        <h1 className="display mt-6 text-2xl">Bağlantı yok</h1>
        <p className="muted mt-3">
          Şu anda internete bağlı görünmüyorsun. Randevu saatleri canlı olarak kontrol edildiği için
          bağlantı gelince devam edebilirsin.
        </p>
        <RetryButton />
      </div>
    </main>
  );
}
