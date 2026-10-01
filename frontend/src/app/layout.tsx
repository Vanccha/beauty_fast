import type { Metadata, Viewport } from 'next';

import { ServiceWorkerRegister } from '@/components/pwa/ServiceWorkerRegister';

import './globals.css';

export const metadata: Metadata = {
  title: 'Aurora Beauty Studio — Randevu',
  description:
    'Akıllı randevu sistemi: paket süresi hesaplayan, ustanın bekleme sürelerini değerlendiren ve slotu veritabanı seviyesinde kilitleyen kuaför randevu uygulaması.',
  applicationName: 'Aurora',
  // PWA: manifest `app/manifest.ts` tarafından otomatik bağlanır.
  // iOS manifestteki simgeleri okumaz; ana ekran simgesi ve başlık ayrıca verilir.
  appleWebApp: {
    capable: true,
    title: 'Aurora',
    statusBarStyle: 'default',
  },
  icons: {
    icon: [
      { url: '/icons/icon.svg', type: 'image/svg+xml' },
      { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
    ],
    apple: [{ url: '/icons/apple-touch-icon.png', sizes: '180x180' }],
  },
  formatDetection: { telephone: false },
};

/**
 * Mobile-first: `maximumScale` kısıtlanmaz (erişilebilirlik — kullanıcı
 * yakınlaştırabilmelidir), ancak `viewportFit` ile çentikli ekranlarda
 * güvenli alan kullanılır.
 */
export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',
  themeColor: '#77496a',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr">
      <body className="min-h-dvh antialiased">
        {children}
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
