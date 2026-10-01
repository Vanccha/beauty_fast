# Aurora Beauty Studio — Arayüz (Next.js)

Next.js 15 (App Router) + Tailwind 4 ile yazılmış müşteri sitesi ve
personel paneli. **Bu uygulama veritabanına hiçbir zaman doğrudan
erişmez** — tüm veri `../backend/` altındaki FastAPI sunucusundan
`/api/*` üzerinden gelir. Backend'in API sözleşmesi, mimarisi ve
algoritmaları için bkz. [`../backend/README.md`](../backend/README.md).

## Kurulum

Backend `:8000` portunda ayakta olmalı (bkz.
[`../backend/README.md`](../backend/README.md#kurulum)).

```bash
cd frontend
npm install
npm run photos           # vitrin fotoğrafları (bir kez; seed'den ÖNCE çalıştır)
npm run dev              # http://localhost:3000
```

`npm run photos` internet erişimi ister ve `backend`'de `python -m
app.seed` çalıştırılmadan **önce** yapılmalıdır: seed, personel ve
portfolyo görselleri için `public/photos/` klasörünü okur; fotoğraf
indirilmemişse üretilmiş SVG yer tutuculara düşer. Fotoğrafları
sonradan indirdiyseniz backend'de seed'i yeniden çalıştırın.

### Komutlar (`package.json`)

| Komut | Ne yapar |
|---|---|
| `npm run dev` | Geliştirme sunucusu (`next dev`, `:3000`) |
| `npm run build` | Üretim derlemesi |
| `npm run start` | Derlenmiş uygulamayı çalıştırır |
| `npm run lint` | `next lint` |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run photos` | `scripts/fetch-photos.mjs` — Unsplash'ten vitrin fotoğraflarını indirir |

### Ortam değişkeni

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `API_URL` | `http://127.0.0.1:8000` | Backend adresi. Hem sunucu tarafı çağrılar (`server-api.ts`) hem de `next.config.mjs` içindeki `/api/*` ve `/uploads/*` rewrite'ları bunu kullanır. Farklı bir portta/host'ta çalışan backend'e işaret etmek için `frontend/.env.local` içine `API_URL=http://...` yazılabilir. |

## Backend ile nasıl konuşur?

Üç ayrı istemci vardır, her biri farklı bir bileşen türü için:

| Dosya | Kimin için | Nasıl çalışır |
|---|---|---|
| `src/lib/server-api.ts` | **Sunucu bileşenleri** (`async function Page()`, layout'lar) | `serverApi<T>(path)` doğrudan `API_URL`'e (backend, `:8000`) sunucudan sunucuya istek atar; tarayıcının çerezlerini (`cookies()` ile) isteğe **kendi elle ekler** ki FastAPI tarafındaki yetki kapıları (`require_staff`, `require_customer`) aynı şekilde çalışsın. `{ok, data}` zarfını açar, hata durumunda `ApiError` fırlatır. `serverApiOrNull` hataları yutup `null` döner ("oturum yoksa misafir göster" gibi akışlar için). |
| `src/lib/admin-api.ts` | **Panel sayfaları** (`admin/(panel)/**`) | `adminApi<T>(path)`, `serverApi`'yi sarar; `401`/`UNAUTHORIZED` alırsa `/admin/giris`'e yönlendirir. Yetki kapısı asıl olarak `admin/(panel)/layout.tsx`'tedir; bu sarmalayıcı, Next.js'in layout ve sayfayı paralel işlemesinden doğabilecek yarış durumuna karşı ek güvencedir. |
| `src/lib/api-client.ts` | **İstemci bileşenleri** (`'use client'`) | `apiGet`/`apiSend`/`apiUpload`, tarayıcıdan aynı origin üzerinden `/api/...`'ye `fetch` atar — çerezler tarayıcı tarafından otomatik eklenir. `next.config.mjs`'teki `rewrites()` bu isteği backend'e yönlendirir. Hatalar `ApiError`'a çevrilir (`error.code` üzerinden `MEMBERSHIP_REQUIRED` → giriş modalı, `SLOT_TAKEN` → slot ızgarasını tazele gibi özel davranışlar tetiklenir). Ayrıca `timeLabel`, `formatTl`, `durationLabel` gibi görüntüleme yardımcılarını da barındırır. |

`next.config.mjs` içindeki `rewrites()`:

```js
{ source: '/api/:path*', destination: `${API_URL}/api/:path*` },
{ source: '/uploads/:path*', destination: `${API_URL}/uploads/:path*` },
```

Bu sayede tarayıcı her zaman tek origin (`localhost:3000`) görür;
`httpOnly` oturum çerezleri CORS/SameSite sorunu olmadan taşınır ve
istemci bileşenleri backend'in gerçek adresini hiç bilmez.

## Rota haritası

Parantezli klasörler (`(shop)`, `(panel)`) Next.js *route group*'tur —
URL'e yansımaz.

### Müşteri sitesi — `src/app/(shop)/`

| URL | Dosya | Kullandığı backend uçları |
|---|---|---|
| `/` | `page.tsx` | `GET /api/showcase`, `GET /api/me` |
| *(tüm shop sayfaları)* | `layout.tsx`, `site-header.tsx`, `nav-link.tsx` | `GET /api/showcase`, `GET /api/me` (kabuk: üst bar, alt gezinme, footer) |
| `/giris` | `giris/page.tsx` + `login-form.tsx` | `GET /api/me` · `POST /api/auth/otp/send`, `POST /api/auth/otp/verify` |
| `/randevu` | `randevu/page.tsx` + `booking-flow.tsx` | `GET /api/catalog/services`, `GET /api/me` · `POST /api/availability`, `GET /api/slots/lock/active`, `POST /api/slots/lock`, `DELETE /api/slots/lock/{id}`, `GET /api/catalog/staff?serviceIds=`, `POST /api/slots/view`, `POST /api/appointments`, `POST /api/appointments/{id}/design` |
| `/hesabim` | `hesabim/page.tsx` + `actions.tsx` + `review-form.tsx` | `GET /api/me`, `GET /api/appointments/mine`, `GET /api/me/album` · `PATCH /api/appointments/{id}` (iptal), `POST /api/auth/logout`, `POST /api/reviews` |
| `/portfolyo` | `portfolyo/page.tsx` | `GET /api/portfolio?category=` |
| `/yorumlar` | `yorumlar/page.tsx` | `GET /api/reviews?...`, `GET /api/showcase` |

### Personel paneli — `src/app/admin/`

| URL | Dosya | Kullandığı backend uçları |
|---|---|---|
| `/admin/giris` | `giris/page.tsx` + `staff-login-form.tsx` | `GET /api/me` · `POST /api/auth/staff/login` |
| *(tüm panel sayfaları)* | `(panel)/layout.tsx` + `nav.tsx` | `GET /api/me` (yetki kapısı — `staff` yoksa `/admin/giris`'e yönlendirir), `GET /api/showcase` · `POST /api/auth/logout` |
| `/admin` | `(panel)/page.tsx` | `GET /api/admin/dashboard` |
| `/admin/takvim` | `takvim/page.tsx` + `calendar-board.tsx` | `GET /api/admin/calendar?date=` · `PATCH /api/admin/appointments/{id}/move`, `PATCH /api/admin/appointments/{id}/status` |
| `/admin/musteriler` | `musteriler/page.tsx` | `GET /api/admin/customers?...` |
| `/admin/musteriler/[id]` | `musteriler/[id]/page.tsx` + `crm-editors.tsx` | `GET /api/admin/customers/{id}` · `POST`/`DELETE /api/admin/customers/{id}/allergy`, `/note`, `/photo` |
| `/admin/stok` | `stok/page.tsx` + `stock-row.tsx` | `GET /api/admin/inventory` · `PATCH /api/admin/inventory` |
| `/admin/kampanyalar` | `kampanyalar/page.tsx` + `campaign-toggle.tsx` | `GET /api/admin/campaigns` · `PATCH /api/admin/campaigns` |
| `/admin/hatirlatmalar` | `hatirlatmalar/page.tsx` + `sweep-button.tsx` | `GET /api/admin/reminder-rules`, `GET /api/admin/notifications?limit=25` · `POST /api/cron/sweep` |
| `/admin/firsat-saatleri` | `firsat-saatleri/page.tsx` | `GET /api/admin/stats/opportunity` |
| `/admin/portfolyo` | `portfolyo/page.tsx` + `portfolio-manager.tsx` | `GET /api/admin/portfolio` · `POST /api/admin/portfolio` (yükleme), `DELETE /api/admin/portfolio?id=` |
| `/admin/yorumlar` | `yorumlar/page.tsx` + `review-controls.tsx` | `GET /api/admin/reviews` · `PATCH /api/admin/reviews/{id}` |
| `/admin/whatsapp` | `whatsapp/page.tsx` + `whatsapp-connect.tsx` | `GET /api/admin/messaging/status` · `POST /api/admin/messaging/qr` · `POST /api/admin/messaging/logout` (QR ile numara bağlama; yalnızca OWNER bağlar) · `GET/PUT /api/admin/messaging/welcome` (ilk mesajda karşılama) |

### Kök dosyalar

| Dosya | Ne işe yarar |
|---|---|
| `src/app/layout.tsx` | Kök HTML iskeleti, `<title>`/`<meta>` (`metadata`), viewport ayarları (çentikli ekranlar için `viewportFit: 'cover'`). |
| `src/app/globals.css` | Tailwind 4 girişi + genel stil tanımları (renk paleti, `.btn-primary`, `.page-shell` gibi yardımcı sınıflar). |

### `src/lib/` — geri kalan yardımcılar

| Dosya | Ne işe yarar |
|---|---|
| `config.ts` | Ortam değişkenlerinin tek okuma noktası (soft-lock TTL, slot ızgarası gibi — backend'deki `config.py` ile aynı varsayılanlar, görüntüleme amaçlı). |
| `intervals.ts` | Aralık cebiri — backend'deki `app/intervals.py`'nin istemci tarafı karşılığı (saf, testli). |
| `time.ts` | Tarih/saat yardımcıları — `"YYYY-MM-DD"` + gün içi dakika temsili, TR biçimlendirme. |
| `hero-image.ts` | Açılış sayfası kahraman görselini çözümler: `public/hero.jpg` → `public/photos/hero.jpg` → `public/hero.svg` (illüstrasyon) sırasıyla dener. |
| `site-photos.ts` | Vitrin fotoğraflarını `public/photos/` altından okur (`photo`, `photoOrFallback`, `photoSet`); hiçbiri yoksa `hero.svg`'ye düşer. |

### `src/components/`

| Dosya | Ne işe yarar |
|---|---|
| `engagement/EngagementBadge.tsx` | "3 kişi bu saate baktı", fırsat saati ve gölge doldurma rozetleri — gösterilen her sayı gerçek bir veritabanı kaydından gelir, `Customer.engagementOptIn === false` ise render edilmez. |
| `engagement/TierProgress.tsx` | Sadakat seviyesi ilerleme çubuğu (`LoyaltyEntry` defterinden hesaplanan gerçek bakiye). |
| `marketing/ReviewCard.tsx` | Tek bir müşteri yorumu kartı (baş harf avatarı, "doğrulanmış randevu" rozeti). |
| `marketing/Stars.tsx` | Erişilebilir yıldız göstergesi (ondalık puan desteği, `aria-hidden` + ekran okuyucu metni). |

## Randevu akışı ve giriş-sonrası devam (login-resume)

`src/app/(shop)/randevu/booking-flow.tsx` tek bir istemci bileşeninde 5
adımlık akışı yönetir: hizmet seçimi → usta seçimi (opsiyonel) → saat
seçimi (`POST /api/availability` + `POST /api/slots/lock`) → notlar/tasarım
→ onay (`POST /api/appointments`).

Misafir kullanıcı onay adımında `MEMBERSHIP_REQUIRED` alırsa:

1. O ana kadarki tüm seçim (hizmetler, usta, saat, kilit id'si, notlar,
   tasarım linki) `sessionStorage`'a `randevu-taslak-v1` anahtarıyla
   yazılır (en fazla 2 saatlik taslaklar geçerli sayılır).
2. Kullanıcı `/giris?next=/randevu?resume=1&services=...` adresine
   yönlendirilir.
3. OTP ile giriş tamamlanınca `?resume=1` ile `/randevu`'ya dönülür;
   sayfa taslağı `sessionStorage`'dan geri okur.
4. Kilit hâlâ geçerliyse (`GET /api/slots/lock/active` aynı
   `viewer_key` çerezini doğrular) kullanıcı doğrudan onay adımına
   döner — hizmet/usta/saat seçimini tekrarlamaz. Kilit süresi
   dolmuşsa aynı saat yeniden kilitlenmeye çalışılır.

Bu davranış, backend'de düzeltilen "kendi kilidin kendi saatini
gizliyor" hatasının (bkz.
[`../backend/README.md`](../backend/README.md#düzeltilen-hatalar))
arayüz tarafındaki tamamlayıcısıdır.

## Fotoğraflar

- `scripts/fetch-photos.mjs` (`npm run photos`), Unsplash'ten sabit bir
  fotoğraf listesini `public/photos/` altına indirir. Depoya gömülü
  değildir (~15 MB), var olan bir dosyanın üzerine `--force` verilmeden
  yazmaz. Kaynak künyesi: [`public/photos/CREDITS.md`](public/photos/CREDITS.md).
- `src/lib/site-photos.ts`, bu klasördeki dosyaları okuyup vitrine
  (açılış sayfası, portfolyo, personel kartları) besler; fotoğraf
  indirilmemişse çizilmiş `public/hero.svg` illüstrasyonuna düşer —
  sistem hiçbir koşulda çökmez.
- `src/lib/hero-image.ts`, yalnızca açılış sayfasının kahraman
  görseli için ayrı bir öncelik sırası uygular: salonun elle koyduğu
  `public/hero.jpg` > indirilen `public/photos/hero.jpg` > illüstrasyon.

## İlgili dokümanlar

- [`../README.md`](../README.md) — proje geneli, hızlı başlangıç, depo yapısı.
- [`../backend/README.md`](../backend/README.md) — API sözleşmesi, zamanlama motoru, veri modeli, testler.

## PWA (mobil / tablet uygulaması)

Site telefona ve tablete "uygulama" olarak yüklenebilir (Android/Chrome: **Yükle** önerisi; iOS/iPadOS Safari: **Paylaş → Ana Ekrana Ekle**).

| Dosya | Görev |
| --- | --- |
| `src/app/manifest.ts` | Uygulama bildirimi (ad, renkler, simgeler, kısayollar) |
| `public/sw.js` | Service worker — önbellek stratejileri dosyanın başında açıklanmıştır |
| `src/app/offline/` | Bağlantı yokken gösterilen sayfa |
| `src/components/pwa/` | SW kaydı, "ana ekrana ekle" önerisi |
| `public/icons/icon.svg` | Simge kaynağı → `npm run icons` ile PNG'ler üretilir |

- Service worker **yalnızca `npm run build && npm start`** ile çalışır; `npm run dev` altında kaydedilmez.
- `/api/*` hiçbir zaman önbellekten servis edilmez (canlı müsaitlik); kişisel sayfalar ve `/admin` önbelleğe alınmaz.
- Önbellek davranışını değiştiren bir yayında `public/sw.js` içindeki `VERSION` değerini artır.
- Kurulum için HTTPS gerekir (`localhost` hariç). Telefonda yerel ağ IP'siyle test ederken tarayıcı yükleme önermez.
