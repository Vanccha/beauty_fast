/**
 * Aurora — service worker (PWA).
 *
 * Bilerek bağımlılıksız ve küçük tutuldu. Önbellekleme stratejileri:
 *
 *   /api/*, RSC istekleri           → DOKUNULMAZ (her zaman ağ).
 *       Randevu saatleri, slot kilitleri ve oturumlar canlı olmalı;
 *       bayat bir müsaitlik bilgisi göstermek çift rezervasyona yol açar.
 *   /_next/static/*                 → önce önbellek (dosya adları hash'li, değişmez).
 *   /photos, /icons, /uploads, svg  → bayatken-yenile (stale-while-revalidate).
 *   Sayfa gezintileri               → önce ağ; ağ yoksa önbellekteki kopya,
 *                                     o da yoksa /offline.
 *
 * Kişisel sayfalar (/randevularim, /hesabim, /giris, /randevu) ve personel paneli (/admin)
 * ÖNBELLEĞE ALINMAZ — paylaşılan bir tablette başka birinin bilgisi
 * görünmesin; çevrimdışıyken bunların yerine doğrudan /offline açılır.
 *
 * Web Push: `push` olayı bildirimi gösterir, `notificationclick` açık bir /admin
 * sekmesini odaklayıp ilgili sayfaya götürür (yoksa yeni pencere açar).
 * `?push-only` ile kaydedilen kopya (yalnızca `next dev` altında) önbelleğe hiç
 * dokunmaz; sadece bildirim olaylarını işler.
 *
 * Yeni sürüm yayınlarken VERSION değerini artırmak eski önbellekleri temizler.
 */
const VERSION = 'v3';
/** Geliştirmede kullanılan, önbelleksiz kopya. */
const PUSH_ONLY = new URL(self.location.href).searchParams.has('push-only');
const STATIC_CACHE = `aurora-static-${VERSION}`;
const PAGE_CACHE = `aurora-pages-${VERSION}`;
const MEDIA_CACHE = `aurora-media-${VERSION}`;

const OFFLINE_URL = '/offline';
const PRECACHE = [OFFLINE_URL, '/icons/icon-192.png', '/icons/icon-512.png', '/manifest.webmanifest'];

/** Çevrimdışı da gösterilebilecek herkese açık sayfalar. */
const CACHEABLE_PAGES = ['/', '/portfolyo', '/yorumlar'];

const MEDIA_LIMIT = 120;

self.addEventListener('install', (event) => {
  if (PUSH_ONLY) {
    event.waitUntil(self.skipWaiting());
    return;
  }
  event.waitUntil(
    caches
      .open(STATIC_CACHE)
      .then(async (cache) => {
        await cache.addAll(PRECACHE);
        await precacheOfflineAssets(cache);
      })
      .then(() => self.skipWaiting()),
  );
});

/**
 * /offline sayfasının HTML'i tek başına yetmez: sayfanın JS ve CSS
 * parçaları da önbellekte olmalı, yoksa çevrimdışıyken "ChunkLoadError"
 * ile çöker. Dosya adları her derlemede değiştiği için listeyi elle
 * tutmak yerine önbelleğe alınan HTML'in içinden okunur.
 */
async function precacheOfflineAssets(cache) {
  const response = await cache.match(OFFLINE_URL);
  if (!response) return;
  const html = await response.text();
  const assets = new Set();
  // Hem <script src="/_next/static/..."> hem de RSC yükündeki "static/chunks/..." biçimi.
  for (const [match] of html.matchAll(/(?:\/_next\/)?static\/(?:chunks|css|media)\/[^"'\\\s)]+/g)) {
    assets.add(match.startsWith('/_next/') ? match : `/_next/${match}`);
  }
  await cache.addAll([...assets]);
}

self.addEventListener('activate', (event) => {
  const keep = new Set([STATIC_CACHE, PAGE_CACHE, MEDIA_CACHE]);
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => !keep.has(k)).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  if (PUSH_ONLY) return;
  const { request } = event;
  if (request.method !== 'GET') return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  const path = url.pathname;

  // Canlı veri: asla önbellekten servis edilmez.
  if (path.startsWith('/api/')) return;
  // Next istemci gezintisi (RSC yükü). Çevrimdışıysa Next tam sayfa
  // yüklemeye düşer, o da aşağıdaki gezinti kuralına takılır.
  if (request.headers.get('RSC') === '1' || url.searchParams.has('_rsc')) return;

  if (request.mode === 'navigate') {
    event.respondWith(handleNavigation(request, path));
    return;
  }

  if (path.startsWith('/_next/static/')) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  if (
    path.startsWith('/photos/') ||
    path.startsWith('/icons/') ||
    path.startsWith('/uploads/') ||
    path.startsWith('/_next/image') ||
    path === '/hero.svg'
  ) {
    event.respondWith(staleWhileRevalidate(event, request, MEDIA_CACHE));
  }
});

async function handleNavigation(request, path) {
  const cacheable = CACHEABLE_PAGES.includes(path);
  try {
    const response = await fetch(request);
    if (cacheable && response.ok) {
      const cache = await caches.open(PAGE_CACHE);
      // Sorgu dizesi (ör. ?source=pwa) farklı kopya üretmesin.
      await cache.put(path, response.clone());
    }
    return response;
  } catch {
    if (cacheable) {
      const cached = await caches.match(path, { cacheName: PAGE_CACHE });
      if (cached) return cached;
    }
    const offline = await caches.match(OFFLINE_URL, { cacheName: STATIC_CACHE });
    return offline ?? new Response('Çevrimdışı', { status: 503, headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
  }
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

async function staleWhileRevalidate(event, request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  const network = fetch(request)
    .then(async (response) => {
      if (response.ok) {
        await cache.put(request, response.clone());
        await trimCache(cache, MEDIA_LIMIT);
      }
      return response;
    })
    .catch(() => undefined);

  if (cached) {
    event.waitUntil(network);
    return cached;
  }
  return (await network) ?? Response.error();
}

/** En eski girdileri silerek önbelleği sınırda tutar (FIFO). */
async function trimCache(cache, limit) {
  const keys = await cache.keys();
  for (let i = 0; i < keys.length - limit; i++) await cache.delete(keys[i]);
}

// ---------------------------------------------------------------------
// Web Push
// ---------------------------------------------------------------------

self.addEventListener('push', (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : '' };
  }
  const title = data.title || 'Aurora';
  const options = {
    body: data.body || '',
    icon: '/icons/icon-192.png',
    badge: '/icons/icon-192.png',
    // Aynı etiketli bildirim öncekinin yerine geçer (yinelenenler birikmez).
    tag: data.tag || undefined,
    renotify: Boolean(data.tag),
    data: { url: data.url || '/admin' },
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || '/admin', self.location.origin);
  event.waitUntil(
    (async () => {
      const all = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      // Önce açık bir panel sekmesi, yoksa herhangi bir sekme.
      const existing = all.find((c) => new URL(c.url).pathname.startsWith('/admin')) || all[0];
      if (existing) {
        await existing.focus();
        if ('navigate' in existing) {
          try {
            await existing.navigate(target.href);
          } catch {
            /* navigate desteklenmiyorsa odaklamak yeterli */
          }
        }
        return;
      }
      await self.clients.openWindow(target.href);
    })(),
  );
});
