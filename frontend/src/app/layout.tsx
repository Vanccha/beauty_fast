import type { Metadata, Viewport } from 'next';
import { Fraunces, Manrope } from 'next/font/google';

import { ServiceWorkerRegister } from '@/components/pwa/ServiceWorkerRegister';

import './globals.css';

const fraunces = Fraunces({ subsets: ['latin', 'latin-ext'], display: 'swap', variable: '--font-fraunces' });
const manrope = Manrope({ subsets: ['latin', 'latin-ext'], display: 'swap', variable: '--font-manrope' });

export const metadata: Metadata = {
  title: 'Aurora Beauty Studio — Randevu',
  description:
    'Kendinize ayırdığınız en güzel saat. Saç, tırnak, kaş ve cilt bakımında uygun saati görün, dakikası dakikasına planlanan randevunuzu alın.',
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
  themeColor: '#6E2B3A',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="tr" data-scroll-behavior="smooth" className={`${fraunces.variable} ${manrope.variable}`}>
      <body className="min-h-dvh antialiased">
        {children}
        <ServiceWorkerRegister />
      </body>
    </html>
  );
}
