import type { Metadata, Viewport } from 'next';

import './globals.css';

export const metadata: Metadata = {
  title: 'Aurora Beauty Studio — Randevu',
  description:
    'Akıllı randevu sistemi: paket süresi hesaplayan, ustanın bekleme sürelerini değerlendiren ve slotu veritabanı seviyesinde kilitleyen kuaför randevu uygulaması.',
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
      <body className="min-h-dvh antialiased">{children}</body>
    </html>
  );
}
