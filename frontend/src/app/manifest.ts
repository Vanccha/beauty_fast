import type { MetadataRoute } from 'next';

/**
 * Web uygulaması bildirimi (PWA). Next bunu `/manifest.webmanifest`
 * olarak servis eder ve `<link rel="manifest">` etiketini kendisi ekler.
 *
 * `orientation` bilerek kısıtlanmaz: tablette takvim yatayda,
 * telefonda randevu akışı dikeyde kullanılır.
 *
 * Simgeler `public/icons/icon.svg` kaynağından `npm run icons` ile üretilir.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: '/',
    name: 'Aurora Beauty Studio',
    short_name: 'Aurora',
    description: 'Kuaför ve güzellik randevunu saniyeler içinde al, randevularını takip et.',
    lang: 'tr',
    dir: 'ltr',
    start_url: '/?source=pwa',
    scope: '/',
    display: 'standalone',
    orientation: 'any',
    background_color: '#F7F3EE',
    theme_color: '#6E2B3A',
    categories: ['beauty', 'lifestyle', 'business'],
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      { src: '/icons/maskable-192.png', sizes: '192x192', type: 'image/png', purpose: 'maskable' },
      { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
    ],
    // Ana ekran simgesine uzun basınca açılan kısayollar.
    shortcuts: [
      {
        name: 'Randevu al',
        short_name: 'Randevu',
        url: '/randevu?source=pwa',
        icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }],
      },
      {
        name: 'Randevularım',
        short_name: 'Hesabım',
        url: '/hesabim?source=pwa',
        icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }],
      },
      {
        name: 'Salon takvimi (personel)',
        short_name: 'Takvim',
        url: '/admin/takvim?source=pwa',
        icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }],
      },
    ],
  };
}
