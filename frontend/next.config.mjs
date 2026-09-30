/** @type {import('next').NextConfig} */

/**
 * Arayüz (bu uygulama) ile backend (FastAPI, `../backend/app`) ayrı süreçlerdir.
 *
 * `/api/*` ve `/uploads/*` istekleri Next üzerinden backend'e
 * YÖNLENDİRİLİR. Böylece:
 *   - tarayıcı her zaman tek origin (localhost:3000) görür,
 *   - httpOnly oturum çerezleri sorunsuz taşınır (CORS/SameSite derdi yok),
 *   - istemci bileşenleri `fetch('/api/...')` çağrılarını DEĞİŞTİRMEDEN kullanır.
 */
const API_URL = process.env.API_URL ?? 'http://127.0.0.1:8000';

const nextConfig = {
  reactStrictMode: true,

  async rewrites() {
    return [
      { source: '/api/:path*', destination: `${API_URL}/api/:path*` },
      // Yüklenen görseller backend tarafından servis edilir (tamamen lokal).
      { source: '/uploads/:path*', destination: `${API_URL}/uploads/:path*` },
    ];
  },
};

export default nextConfig;
