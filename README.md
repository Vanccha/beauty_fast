# Aurora Beauty Studio — Akıllı Salon Randevu Sistemi

Bu depo, [`Vanccha/beauty_center_system`](https://github.com/Vanccha/beauty_center_system)
adlı Next.js + Prisma projesinin bir portudur: **arayüz Next.js 15'te
kalırken backend Prisma'dan FastAPI + SQLAlchemy'ye taşınmıştır.**
Orijinal repo yalnızca okundu; ona hiçbir yazma işlemi (push/commit/PR)
yapılmadı.

Öne çıkanlar:

- **Zamanlama motoru veritabanı seviyesinde çakışma korumalı.** Aynı
  slota eşzamanlı iki istek geldiğinde biri `UNIQUE` kısıtıyla
  reddedilir — Redis yok, uygulama içi kilit yok.
- **Paketler kesintisiz bloklanır.** 110 dakikalık bir paket asla 60
  dakikalık bir boşluğa önerilmez; hesap üç boyutu (süre, usta
  müsaitliği, kaynak kapasitesi) aynı anda değerlendirir.
- **Shadow blocking.** Saç boyasının ortasındaki 40 dakikalık bekleme
  süresinde usta boşa düşmez; o pencere başka bir müşteriye açılır.
- **Randevu akışındaki üç hata bu portta düzeltildi** ve regresyon
  testleriyle kilitlendi (bkz. [`backend/README.md`](backend/README.md#düzeltilen-hatalar)).
- **KVKK'ya duyarlı risk skoru.** Salonlar arası no-show geçmişi, ham
  telefon numarası tutulmadan HMAC anahtarıyla skorlanır.
- **Az dış bağımlılık.** PostgreSQL (lokalde Docker ile) + yerel dosya
  sistemi; Redis, S3 veya ücretli SMS servisi gerekmez. Doğrulama kodları
  ve hatırlatmalar kendi çalıştırdığınız Evolution API üzerinden WhatsApp
  ile gider.

## Mimari

```
                         ┌──────────────────────┐
  tarayıcı  ───────────► │  Next.js 15 :3000     │
  (kullanıcı)            │  frontend/             │
                         └──────────┬─────────────┘
                                    │ /api/*  ve  /uploads/*
                                    │ (next.config.mjs → rewrites)
                                    ▼
                         ┌──────────────────────┐
                         │  FastAPI :8000         │
                         │  backend/app/           │
                         └──────────┬─────────────┘
                                    │ SQLAlchemy
                                    ▼
                         ┌──────────────────────┐
                         │  PostgreSQL :5432      │
                         │  (docker compose, db)  │
                         └──────────────────────┘
```

Next.js **hiçbir zaman** veritabanına dokunmaz; tüm veri `/api/*`
üzerinden FastAPI'den gelir. Tarayıcı tek bir origin görür
(`localhost:3000`) — `frontend/next.config.mjs` içindeki `rewrites()`
isteği arka planda backend'e (`API_URL`, varsayılan
`http://127.0.0.1:8000`) yönlendirir. Bu sayede oturum çerezleri
CORS/SameSite derdi olmadan taşınır.

## Depo yapısı

```
beauty_fast/
├── backend/    FastAPI + SQLAlchemy + PostgreSQL API sunucusu (zamanlama motoru, CRM, admin panel API'si)
├── frontend/   Next.js 15 (App Router) + Tailwind 4 arayüzü — yalnızca backend'le konuşur
├── README.md   Bu dosya — proje geneli
└── .gitignore
```

Her klasörün kendi README'si vardır: [`backend/README.md`](backend/README.md)
(mimari, algoritmalar, düzeltilen hatalar, API, veri modeli, testler) ve
[`frontend/README.md`](frontend/README.md) (rota haritası, API
istemcileri, randevu akışı).

## Hızlı başlangıç

Gerekenler: Python 3.11+, Node.js 18+ ve Docker (PostgreSQL için).
Önce veritabanını başlatın, sonra iki terminal açın:

```bash
cd backend
docker compose up -d db             # PostgreSQL :5432 (WhatsApp için: --profile whatsapp up -d)
```

### 1) Backend (Terminal 1)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate              # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

copy .env.example .env              # Linux/macOS: cp .env.example .env
```

`.env` içindeki tüm değişkenlerin lokal bir varsayılanı vardır; bu
kopyalama adımı yalnızca demo girişini sabitler (`DEV_OTP_CODE=123456`
— aşağıya bakın). Seed'i **fotoğraflar indirildikten sonra** çalıştırın
(adım 3), sonra sunucuyu başlatın:

```bash
uvicorn app.main:app --reload       # http://localhost:8000
```

### 2) Frontend bağımlılıkları + fotoğraflar (Terminal 2)

```bash
cd frontend
npm install
npm run photos                      # Unsplash'ten vitrin fotoğraflarını indirir (bir kez, seed'den ÖNCE)
```

`npm run photos` internet erişimi ister; atlanırsa sistem çökmez,
çizilmiş SVG yer tutuculara düşer — ama gerçek bir vitrin için önce bu
adımı çalıştırın.

### 3) Demo verisini üret (fotoğraflar indikten sonra, Terminal 1 veya 2)

```bash
cd backend
python -m app.seed                  # deterministik demo verisi (personel, hizmetler, 180 günlük geçmiş...)
```

Fotoğrafları adım 2'den *sonra* indirdiyseniz seed'i yeniden çalıştırın;
personel ve portfolyo fotoğrafları `frontend/public/photos/` altındaki
gerçek dosyaları arar, yoksa üretilmiş SVG'ye düşer.

### 4) Frontend'i başlat (Terminal 2)

```bash
cd frontend
npm run dev                         # http://localhost:3000
```

Artık `http://localhost:3000` üzerinden siteyi, `http://localhost:8000/docs`
üzerinden etkileşimli API dokümanını (Swagger UI) görebilirsiniz.

### Demo giriş bilgileri

| Rol | Telefon | Şifre |
|---|---|---|
| Salon sahibi | `05551110001` | `admin123` |
| Yönetici | `05551110002` | `merve123` |
| Personel | `05551110003` | `zeynep123` |
| Personel | `05551110004` | `selin123` |

Personel/yönetici girişi `/admin/giris` üzerindendir.

**Müşteri girişi şifresizdir.** `/giris` sayfasında demo numaralarından
birini kullanın: `05321010000` … `05321010024` (25 demo müşteri).
"Kod gönder"e bastığınızda:

- `backend/.env` içinde `DEV_OTP_CODE=123456` tanımlıysa (bu değişken
  `backend/.env.example`'da hazır gelir — bkz. `backend/app/config.py`
  içindeki `Config.dev_otp_code`), kod **her zaman `123456`** olur ve
  giriş formuna otomatik yazılır,
- tanımlı değilse rastgele 6 haneli kod üretilir; SMS gönderilmediği
  için kod sunucu konsoluna yazılır ve (`APP_ENV != production` iken)
  API yanıtının `devCode` alanında döner.

## "Hangi dosya ne işe yarar?"

### `backend/app/` — üst düzey modüller

| Dosya | Ne işe yarar |
|---|---|
| `main.py` | FastAPI uygulaması: CORS, router kaydı, hata işleyicileri, `/uploads` statik servisi, kök adresteki basit dizin sayfası. |
| `config.py` | Ortam değişkenlerinin tek okuma noktası; `.env` dosyasını bağımlılıksız okur, tümü için lokal varsayılan tanımlar. `validate_config()` üretimde eksik/zayıf sırlarda uygulamanın açılmasını engeller. |
| `db.py` | SQLAlchemy engine + oturum fabrikası (PostgreSQL); `init_db()` şemayı Alembic ile günceller. |
| `models.py` | 37 tablo, tamamı yorumlu — `Salon`/`Branch`'ten `OccupancyCell`, `PhoneRiskEvent`, `Review`'a kadar tüm veri modeli. |
| `deps.py` | Yetki kapıları: `require_staff`, `require_role`, `require_customer`, `require_any_principal` — hepsi hata fırlatır, sessizce veri sızdırmaz. |
| `http.py` | `{ok, data}` / `{ok:false, error}` API zarfı, `EnvelopeRoute`, genel hata işleyicileri. |
| `errors.py` | `AppError`, `SlotConflictError`, `VersionConflictError` gibi tipli hatalar + unique-ihlali tespiti. |
| `intervals.py` | Saf aralık cebiri (`overlaps`, `subtract`, `saturated_intervals`/sweep-line) — zamanlama motorunun matematiksel tabanı. |
| `time_utils.py` | `now_local()` (salon saat dilimine göre "şimdi"), gün-yerel dakika temsili (`"YYYY-MM-DD"` + dakika), TR tarih/gün adları, ızgaraya yuvarlama. |
| `uploads.py` | Tamamen yerel dosya yükleme: magic-number doğrulama, uuid dosya adı, harici bağlantı sanitizasyonu (XSS'e karşı). |
| `seed.py` | Deterministik demo verisi üretici (`python -m app.seed`) — 6 aylık geçmiş, 450 randevu, 25 müşteri, yorumlar, kampanyalar. |
| `whatsapp.py` | WhatsApp kurulum komutları: `python -m app.whatsapp connect` (QR kodu), `status`, `test <numara>`. |

### `backend/app/api/` — HTTP uçları (iş mantığı içermez)

| Dosya | Uçlar |
|---|---|
| `auth.py` | `POST /api/auth/otp/send`, `/otp/verify`, `/staff/login`, `/logout` |
| `public.py` | `GET /api/me`, `/api/showcase`, `/api/portfolio`, `/api/reviews`, `POST /api/reviews`, `POST /api/cron/sweep` |
| `catalog.py` | `GET /api/catalog/services`, `/api/catalog/staff` |
| `slots.py` | `POST /api/availability`, `POST /api/slots/lock`, `DELETE /api/slots/lock/{id}`, `GET /api/slots/lock/active`, `POST /api/slots/view` |
| `appointments.py` | `POST /api/appointments`, `GET /api/appointments/mine`, `GET/PATCH /api/appointments/{id}`, `POST /api/appointments/{id}/design` |
| `admin.py` | Personel paneli uçlarının tamamı: dashboard, takvim, müşteri/CRM, stok, kampanya, hatırlatma kuralı, bildirim, yorum moderasyonu, fırsat saati istatistiği, portfolyo yönetimi (`require_staff` arkasında). |

### `backend/app/auth/` — kimlik doğrulama

| Dosya | Ne işe yarar |
|---|---|
| `otp.py` | Telefon + 6 haneli kod akışı: kod üretimi/doğrulama, kod başına deneme sayacı, hız sınırlama, geliştirme modunda sabit kod. |
| `password.py` | `hashlib.scrypt` ile şifre hash'leme (bcrypt yerine — ek bağımlılık istemeyen standart kütüphane KDF'i). |
| `rate_limit.py` | Veritabanı tabanlı kayan pencereli deneme sınırı (personel girişi, OTP isteme/doğrulama); tüm worker'lar aynı sayacı paylaşır. |
| `sessions.py` | Opak token + veritabanı kaydı oturum yönetimi; personel/müşteri çerezleri ayrı, ziyaretçi anahtarı (`visitor_key`) soft-lock sahipliği için. |

### `backend/app/core/` — saf zamanlama/CRM algoritmaları (ORM bilmez, birim testli)

| Dosya | Ne işe yarar |
|---|---|
| `types.py` | Motorun ORM'den bağımsız giriş/çıkış tipleri (`ServiceSpec`, `PackageLayout`, `SlotCandidate`...). |
| `package_layout.py` | Bir paketin takvimde kapladığı kesintisiz bloğu ve sıkıştırmayı (compaction) hesaplar. |
| `availability.py` | Bitişik blok bulma: süre + usta müsaitliği + kaynak kapasitesini aynı anda değerlendirir. |
| `occupancy.py` | Doluluk hücresi (`occupancy_cell`) üretimi — yarış koşulu savunmasının veri tarafı. |
| `opportunity.py` | Fırsat saatleri: Bayes shrinkage ile düzeltilmiş doluluk oranından indirim eğrisi. |
| `loyalty.py` | Sadakat puanı hesaplama, seviye eşikleri, atıl puan erimesi. |
| `risk_score.py` | Salonlar arası gölge risk skoru (KVKK uyumlu, HMAC anahtarlı). |
| `segmentation.py` | Müşteri CRM rozetleri: VIP / SADIK / RİSKLİ / UYUYAN / YENİ. |
| `color_affinity.py` | Albüm etiketlerinden zaman ağırlıklı renk eğilimi analizi. |
| `campaigns.py` | JSON kural motoruyla algoritmik kampanya hedefleme (kupon kodu yok). |
| `reminder_rules.py` | Hatırlatma kural motoru — dört formül (`FIXED`/`GROWTH`/`PRODUCT_LIFETIME`/`SEASONAL`). |
| `recommendation.py` | Hizmet öneri sıralaması + gölge pencereye uygun upsell önerisi. |

### `backend/app/services/` — algoritma ↔ veritabanı köprüsü

| Dosya | Ne işe yarar |
|---|---|
| `availability.py` | `core.availability`'yi veritabanıyla besler; müsaitlik sorgusunun HTTP'ye bağlandığı yer. |
| `soft_lock.py` | Geçici slot rezervasyonu (5 dk); `occupancy_cell` unique kısıtıyla çakışma savunması. |
| `appointment.py` | Soft-lock'u kalıcı randevuya çevirme + sürükle-bırak taşıma (optimistic locking). |
| `appointment_status.py` | Randevu durum değişiminin TEK yan etki noktası (iptal/no-show/tamamlama zincirleri). |
| `catalog.py` | Veritabanı satırlarını saf `ServiceSpec`'e çevirir; personel yetkinlik kontrolü burada. |
| `customer_profile.py` | CRM kartının tek okuma noktası: segment + risk + sadakat + renk eğilimi bir arada. |
| `campaign_audience.py` | Bir kampanya kuralının şu anda kaç müşteriyle eşleştiğini hesaplar. |
| `risk.py` | Gölge risk skorunun veritabanı sarmalayıcıları (saf hesap `core/risk_score.py`'dedir). |
| `stock.py` | Hizmet reçetesine göre idempotent stok düşümü (`UNIQUE(appointment_id, item_id)`). |
| `reviews.py` | Yayınlanmış yorumların okunması + özet istatistik (ortalama, dağılım). |
| `portfolio.py` | Panel galerisi yönetim katmanı (kategori/usta seçenekleri, yükleme). |
| `notifications.py` | Bildirim kuyruğunun okunması ve gönderimi (sahiplenme, yeniden deneme, geri çekilme). |
| `whatsapp_inbound.py` | Gelen WhatsApp mesajları: ilk mesajda karşılama, tanıdık kişi defteri. |
| `messaging.py` | Mesaj sürücüleri: `console` (log) ve `evolution` (WhatsApp, Evolution API). |
| `welcome.py` | Kişiselleştirilmiş karşılama metni + salon istatistikleri (uydurma veri yok, gerçek son randevudan türetilir). |

### `backend/tests/` — 201 test

| Dosya | Kapsam |
|---|---|
| `conftest.py` | Test altyapısı — ayrı PostgreSQL veritabanı (`aurora_test`, adı `_test` ile bitmeyen veritabanında çalışmayı reddeder), fikstürler. |
| `test_intervals.py` | Aralık cebiri, sweep-line doygunluk. |
| `test_package_layout.py` | Paket sıkıştırma, gölge pencere, tekrarlı hizmet. |
| `test_availability.py` | Kesintisiz blok kuralı, gölge doldurma, kaynak doygunluğu. |
| `test_scoring.py` | Risk, sadakat, fırsat, segment, renk, kampanya skorlamaları. |
| `test_reminder_rules.py` | Dört hatırlatma formülü + kural önceliği. |
| `test_recommendation.py` | Hizmet öneri sıralaması, gölge upsell. |
| `test_concurrency.py` | Eşzamanlı isteklerden tam 1 başarı; optimistic locking; stok idempotensi. |
| `test_booking_bugfix.py` | Düzeltilen üç hatanın regresyon testleri. |
| `test_booking_login_resume.py` | Misafir kilidinin girişten sonra geçerliliği, kilit sahipliği, `CUSTOMER_OVERLAP`. |
| `test_status_version.py` | Durum değişikliğinin döndürdüğü `version` alanının doğruluğu. |
| `test_api.py` | Uçtan uca API: zarf, yetki kapıları, randevu akışı, yorum kapıları. |
| `test_admin_views.py` | Panel sayfalarını besleyen uçlar: bildirim kuyruğu, galeri listesi, fırsat saati bayrakları. |
| `test_whatsapp_welcome.py` | WhatsApp'ta ilk mesaja karşılama ve "tanıdık kişi" kuralları. |
| `test_kvkk.py` | KVKK: ileti onayı, alerji rızası, veri dökümü, hesap silme (anonimleştirme), saklama süreleri. |
| `test_messaging.py` | WhatsApp (Evolution API) gönderimi: istemci, OTP, kuyruk yeniden denemeleri. |
| `test_security.py` | OTP kaba kuvvet koruması, deneme sınırları, bakım ucu yetkisi, üretim yapılandırma doğrulaması, saat dilimi. |

Ayrıntılı algoritma açıklamaları, düzeltilen hatalar ve API tablosu için
bkz. [`backend/README.md`](backend/README.md).

### `frontend/` — arayüz

| Alan | Ne işe yarar |
|---|---|
| `src/app/(shop)/` | Müşteri arayüzü: ana sayfa, randevu akışı, hesabım, portfolyo, yorumlar, giriş. |
| `src/app/admin/` | Personel paneli: takvim, müşteriler/CRM, stok, kampanya, hatırlatma, fırsat saatleri, portfolyo yönetimi, yorum moderasyonu. |
| `src/lib/server-api.ts` / `admin-api.ts` | Sunucu bileşenlerinin FastAPI'yi çağırdığı, çerezleri ileten yardımcılar. |
| `src/lib/api-client.ts` | İstemci bileşenlerinin `/api/...`'ye attığı isteklerin sarmalayıcısı. |
| `scripts/fetch-photos.mjs` | `npm run photos` — Unsplash'ten vitrin fotoğraflarını indirir. |

Rota haritası, her sayfanın hangi backend uçlarını kullandığı ve randevu
akışının adım adım anlatımı için bkz. [`frontend/README.md`](frontend/README.md).

## Bir istek nasıl akar?

Örnek: kullanıcı randevu adımında bir saat seçip "Bu saati tut"a basar.

1. **`frontend/src/app/(shop)/randevu/booking-flow.tsx`** — istemci
   bileşeni, seçilen hizmetler + saat ile `apiSend('/api/slots/lock', 'POST', ...)`
   çağırır.
2. **`frontend/next.config.mjs`** — `/api/*` isteğini aynı origin
   üzerinden `API_URL`'e (backend, `:8000`) proxy'ler; çerezler bu
   sayede korunur.
3. **`backend/app/api/slots.py`** — `POST /api/slots/lock` ucu isteği
   doğrular (Pydantic modeli), yetki/oturum bilgisini `deps.py`'den
   alır.
4. **`backend/app/services/soft_lock.py`** — `acquire_slot_lock()`,
   paket yerleşimini `core/package_layout.py` ile yeniden hesaplar,
   `occupancy_cell` tablosuna hücre satırları yazar.
5. **`backend/app/core/occupancy.py`** / **`intervals.py`** — saf
   hesaplama; hiçbiri veritabanı bilmez.
6. Yazma başarılıysa `{ok: true, data: {...}}` zarfı döner
   (`backend/app/http.py`); çakışma varsa `SLOT_TAKEN` (409) döner ve
   arayüz slot ızgarasını tazeler.

## Lisans ve teşekkür

Vitrin fotoğrafları [Unsplash](https://unsplash.com) üzerinden Unsplash
License ile alınmıştır (ticari kullanım serbest); kaynak listesi
[`frontend/public/photos/CREDITS.md`](frontend/public/photos/CREDITS.md)
içindedir. Fotoğraflar depoda versiyonlanmaz, `npm run photos` ile
indirilir.
