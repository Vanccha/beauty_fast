# Aurora V2 — Değişenler

**Tarih:** 30 Eylül 2026
**Kapsam:** Ağırlıklı olarak backend (`backend/`). Arayüze admin paneli için bir WhatsApp sayfası eklendi, 3 metin güncellendi (SMS yerine WhatsApp).
**Amaç:** Projeyi sunucuya almadan önce güvenlik açıklarını kapatmak, SQLite'tan PostgreSQL'e taşımak ve OTP ile hatırlatmaları gerçekten gönderebilmek (WhatsApp).

Test sayısı 129'dan 190'a çıktı. Proje artık yalnızca PostgreSQL ile çalışıyor (madde 13); testlerin tamamı PostgreSQL 17'de geçiyor.

---

## Özet

| # | Değişiklik | Önem |
|---|---|---|
| 1 | OTP kodu kaba kuvvetle kırılabiliyordu | 🔴 Kritik güvenlik |
| 2 | OTP isteme sınırı hiç çalışmıyordu (sınırsız SMS) | 🔴 Kritik güvenlik |
| 3 | Üretimde güvensiz varsayılanlar | 🔴 Kritik güvenlik |
| 4 | `/api/cron/sweep` herkese açıktı | 🔴 Güvenlik |
| 5 | Personel girişinde deneme sınırı yoktu | 🔴 Güvenlik |
| 6 | Demo şifreleri ve `/docs` üretimde açıktı | 🟠 Güvenlik |
| 7 | Saat dilimi sunucuya bağlıydı | 🟠 Doğruluk |
| 8 | PostgreSQL'de ortaya çıkacak eşzamanlılık hataları | 🟠 Doğruluk |
| 9 | Alembic ile migration altyapısı | 🟠 Altyapı |
| 10 | PostgreSQL desteği, Docker imajı | 🟢 Altyapı |
| 11 | WhatsApp ile OTP ve hatırlatma gönderimi (Evolution API) | 🟢 Yeni özellik |
| 12 | WhatsApp'ta ilk mesaja otomatik karşılama | 🟢 Yeni özellik |
| 13 | SQLite desteği tamamen kaldırıldı, proje yalnızca PostgreSQL | 🟢 Altyapı |

---

## 🔴 Güvenlik düzeltmeleri

### 1. OTP kaba kuvvet açığı kapatıldı

**Sorun:** Yanlış deneme sayacı yanlış denemeleri saymıyordu. Onun yerine numaraya o pencerede kaç kod üretildiğine bakıyordu. Tek kod isteyen biri için bu sayı hep 1'de kalıyordu. Böylece 5 dakika boyunca sınırsız tahmin yapılabiliyor, yani herhangi bir müşterinin hesabı ele geçirilebiliyordu.

**Çözüm:**
- `verification_code` tablosuna `attempts` alanı eklendi. Bir kod en fazla 5 kez denenebiliyor, sonra geçersiz oluyor. Doğru kod da artık kabul edilmiyor.
- Deneme hakkı, kod karşılaştırılmadan **önce** atomik bir `UPDATE ... WHERE attempts < 5` ile ayrılıyor. Paralel gönderilen istekler de sınırı aşamıyor.
- Kod tek kullanımlık hale getirildi (atomik "sahiplenme"). Aynı kodla gelen ikinci istek reddediliyor.
- Numara başına 15 dakikada 10, IP başına 30 hatalı doğrulama sınırı eklendi. Yeni kod isteyerek deneme hakkını yenilemek de sınırlı.

### 2. OTP isteme sınırı düzeltildi

**Sorun:** "15 dakikada 5 kod" sınırı hiç devreye girmiyordu, çünkü her yeni istek önceki kullanılmamış kodları sayımdan önce siliyordu. Sonuç: bir numaraya sınırsız SMS (SMS bombardımanı ve maliyet).

**Çözüm:** Sayım artık ayrı bir `rate_limit_hit` tablosunda tutuluyor. Numara başına 15 dakikada 5, IP başına 30 istek.

### 3. Üretim için güvenli varsayılanlar

**Sorun:** `APP_ENV=production` ayarlanmayı unutursa OTP kodu API yanıtında (`devCode`) dönüyordu, `DEV_OTP_CODE=123456` herkes için geçerli oluyordu ve çerezler `secure` olmadan gidiyordu. Sırlar boş bırakılırsa depoda açıkça yazan değerlere düşülüyordu.

**Çözüm (`app/config.py`):**
- Geliştirme kolaylıkları yalnızca `APP_ENV` açıkça `development` veya `test` ise açık. Diğer **her değer** (`prod`, `staging`, yazım hatası...) üretim sayılıyor.
- Yeni `validate_config()` fonksiyonu üretimde şu durumlardan birinde uygulamanın **açılmasını engelliyor**:
  - `SESSION_SECRET` veya `PHONE_HASH_SECRET` eksik, lokal varsayılanla aynı ya da 32 karakterden kısa
  - `CRON_SECRET` eksik veya kısa
  - `DEV_OTP_CODE` tanımlı
  - `EVOLUTION_WEBHOOK_URL` tanımlı ama `EVOLUTION_WEBHOOK_SECRET` 32 karakterden kısa
- Şu iki durum **her ortamda** (geliştirmede de) uygulamanın açılmasını engelliyor:
  - `NOTIFICATION_DRIVER` tanınmayan bir değerse (ör. yazım hatası). Aksi hâlde mesajlar sessizce yalnızca log'a yazılırdı.
  - Sürücü `evolution` iken Evolution ayarları eksikse.
- Güvenliği bozmayan ama dikkat isteyen durumlar açılışta uyarı olarak loglanıyor:
  - Mesaj sürücüsü `console` (mesaj gönderilmiyor).
  - `EVOLUTION_WEBHOOK_URL` boş (karşılama mesajı çalışmaz).
  - `PUBLIC_SITE_URL` localhost (müşteriye giden bağlantılar çalışmaz).
- Docker imajında `APP_ENV=production` varsayılan.

### 4. Bakım ucu (`/api/cron/sweep`) korumaya alındı

**Sorun:** Adresi bilen herkes bildirim kuyruğunu tetikleyebiliyordu. GET ile bile çalışıyordu.

**Çözüm:**
- İki yoldan biri gerekiyor: `X-Cron-Secret` başlığı (zamanlayıcı için, sabit zamanlı karşılaştırma) ya da en az **MANAGER** rolünde personel oturumu (paneldeki "bakım" düğmesi).
- GET sürümü kaldırıldı.
- Süresi dolan deneme sınırı kayıtlarını da temizliyor.

### 5. Personel girişine deneme sınırı

**Sorun:** Şifreler sınırsız denenebiliyordu. Ayrıca scrypt bilerek pahalı bir algoritma olduğu için sınırsız istek sunucuyu kilitlemenin de bir yoluydu.

**Çözüm:** Numara başına 15 dakikada 5, IP başına 20 hatalı deneme. Sınır dolunca şifre hiç hesaplanmıyor ve doğru şifre de reddediliyor. Başarılı giriş numaranın sayacını sıfırlıyor. Kayıtlı olmayan numarada da aynı davranış var, hesap sayımına kapalı.

Sayaçlar veritabanında tutuluyor (`app/auth/rate_limit.py`). Birden fazla worker veya sunucu aynı sınırları paylaşıyor, Redis gerekmiyor.

### 6. Demo içerik üretimde kapalı

- Demo personel şifrelerini listeleyen kök sayfa (`/`) üretimde 404 dönüyor.
- `/docs`, `/redoc` ve `/openapi.json` üretimde kapalı.
- `python -m app.seed` veritabanını sıfırladığı için üretimde çalışmayı reddediyor.
- CORS izinli origin'leri artık `CORS_ORIGINS` ile ayarlanıyor. Üretimde varsayılan boş; arayüz zaten Next.js rewrite üzerinden aynı origin'den geliyor.

---

## 🟠 Doğruluk düzeltmeleri

### 7. Saat dilimi

**Sorun:** Kodda 43 yerde `datetime.now()` kullanılıyordu, yani sunucunun saat dilimi esas alınıyordu. Sunucular genelde UTC'de çalışır. Böyle bir sunucuda soft-lock süreleri, hatırlatmalar, "bugün" hesabı ve geçmiş tarih kontrolü 3 saat kayardı.

**Çözüm:** `app/time_utils.py` içine `now_local()` eklendi. "Şimdi" artık her zaman salonun saat dilimine göre hesaplanıyor (`APP_TIMEZONE`, varsayılan `Europe/Istanbul`). Veritabanındaki kayıt biçimi değişmedi, mevcut veri etkilenmiyor. Windows'ta saat dilimi verisi için `tzdata` paketi eklendi.

### 8. PostgreSQL'de ortaya çıkacak eşzamanlılık hataları

SQLite'ta `BEGIN IMMEDIATE` tüm yazmaları sıraya dizdiği için aşağıdaki durumlar görünmüyordu. PostgreSQL'de (READ COMMITTED) bunlar gerçek hatalara dönüşürdü:

| Durum | Olası sonuç | Çözüm |
|---|---|---|
| Aynı randevuya "tamamlandı" isteği iki kez gelirse (çift tıklama, sürüm bilgisi gönderilmeden) | Sadakat puanı iki kez yazılır | Durum güncellemesi `status NOT IN (COMPLETED, CANCELLED, NO_SHOW)` koşuluyla yapılıyor, ikinci istek 0 satır etkiliyor |
| İki randevu aynı malzemeyi aynı anda düşerse | Stok düşümlerinden biri kaybolur | Stok satırı `SELECT ... FOR UPDATE` ile kilitleniyor. Kilitler `item_id` sırasıyla alınıyor, böylece deadlock oluşmuyor |
| Manuel stok düzeltmesi | Aynı kayıp güncelleme | Aynı kilit |
| Aynı müşterinin iki randevusu aynı anda tamamlanırsa | Puanlardan biri kaybolur | Müşteri satırı kilitleniyor |

Unique ihlali tespiti (`is_unique_violation`) PostgreSQL'de artık SQLSTATE `23505` koduna bakıyor, mesaj metnine güvenmiyor.

---

## 🟢 Altyapı

### 9. Alembic migration'ları

- Şema artık `create_all` ile değil, `backend/migrations/` altındaki migration'larla yönetiliyor.
  - `0001`: v1 şeması (36 tablo)
  - `0002`: `verification_code.attempts` alanı ve `rate_limit_hit` tablosu (madde 1, 2, 5)
  - `0003`: `scheduled_notification` tablosuna yeniden deneme alanları (madde 11)
  - `0004`: `whatsapp_contact` tablosu ve `salon` tablosuna karşılama mesajı alanları (madde 12)
- Migration'lar modellerle birebir uyumlu (`alembic check` farksız). `0004`'teki boolean varsayılan değeri PostgreSQL'de de çalışacak şekilde yazıldı.
- Geliştirmede sunucu ve seed açılışta migration'ları kendiliğinden çalıştırıyor. Üretimde çalıştırmıyor: birden fazla worker aynı anda şema değiştirmeye çalışmasın diye bu dağıtım adımı (`alembic upgrade head`) olarak yapılıyor. Docker imajı bunu açılışta yapıyor.

### 10. PostgreSQL ve Docker

- `psycopg` sürücüsü eklendi. `postgres://...` biçimindeki adresler (Render, Railway, Heroku vb.) otomatik olarak doğru sürücüye çevriliyor.
- `backend/docker-compose.yml`: lokal PostgreSQL 17, ayrı bir `aurora_test` veritabanıyla birlikte.
- Test paketi Docker'daki `aurora_test` veritabanında koşuyor (bkz. madde 13).
- `backend/Dockerfile`: üretim imajı. Root olmayan kullanıcıyla çalışıyor, yüklemeler için kalıcı volume (`/data/uploads`) kullanıyor, `--proxy-headers` açık.
- Demo seed verisi PostgreSQL'e yüklendi ve tüm panel/genel GET uçları orada da hatasız döndü.

---

## 🟢 Yeni özellik

### 11. WhatsApp ile mesaj gönderimi (Evolution API)

V1'de hiçbir mesaj gerçekten gönderilmiyordu, OTP kodları ve hatırlatmalar yalnızca konsola yazılıyordu. Artık WhatsApp üzerinden gidiyorlar.

**Tercih:** Numara QR kodla bağlanıyor (Evolution API, Baileys modu). Meta'nın resmi Cloud API'si kullanılmıyor, bu yüzden mesaj başına ücret yok.

**Bedeli:** Bu resmi bir entegrasyon değil. WhatsApp numarayı kısıtlayabilir veya kapatabilir. Riski azaltmak için:
- Yalnızca bilgilendirme mesajları gönderiliyor (OTP, randevu hatırlatması). **Toplu kampanya gönderimi bilerek yok.**
- Kuyruk mesajları arasında bekleme var (varsayılan 1,5 sn) ve bir bakım çalıştırmasında en fazla 20 mesaj gidiyor.
- Salonun ana numarası yerine ayrı bir numara kullanılmalı.

**Yapılanlar:**
- **Sürücü katmanı** (`app/services/messaging.py`): `NOTIFICATION_DRIVER=console` mesajları log'a yazıyor, `evolution` WhatsApp'tan gönderiyor. Sürücü adı tanınmıyorsa ya da Evolution ayarları eksikse uygulama hiç açılmıyor.
- **OTP:**
  - Kod WhatsApp mesajı olarak gidiyor: "*Salon adı* doğrulama kodunuz: **123456**".
  - Numara bağlı değilse istek hemen `503 DELIVERY_FAILED` dönüyor ve müşterinin kod isteme hakkından düşmüyor.
  - Gönderim başarısız olursa `502 DELIVERY_FAILED` dönüyor.
  - Bu kontrolün nedeni denemede ortaya çıktı: Evolution API, bağlı olmayan numaraya gönderilen mesajda hata dönmek yerine 30 saniyeden uzun süre asılı kalıyor.
- **Hatırlatma kuyruğu:**
  - V1'de kuyruktaki mesajlar gönderilemese bile `SENT` olarak işaretleniyordu. Artık gerçek sonuç kaydediliyor.
  - Kayıtlar önce sahipleniliyor (`SENDING`). Aynı anda çalışan iki bakım işi aynı mesajı iki kez göndermiyor (PostgreSQL'de `FOR UPDATE SKIP LOCKED`).
  - Ağ çağrısı veritabanı transaction'ı dışında yapılıyor.
  - Başarısız mesaj 5, 10, 20 ve 40 dakika arayla yeniden deneniyor, 5. denemede `FAILED` oluyor. Son hata kaydediliyor ve panelde gösterilebiliyor.
  - Bağlantı kopuksa hiç deneme yapılmıyor, deneme hakları harcanmıyor.
  - Gönderim sırasında süreç çökerse kayıt 10 dakika sonra yeniden sahipleniliyor. Mesaj kaybolmuyor, nadiren iki kez gidebiliyor.
- **Admin paneli, WhatsApp sayfası** (`/admin/whatsapp`, menüde 💬):
  - Bağlantı durumunu gösteriyor: Bağlı / Bağlanmayı bekliyor / Bağlı değil / Henüz kurulmadı / Geçide ulaşılamıyor.
  - Salon sahibi (OWNER) **"QR kodu ile bağla"** düğmesiyle QR'ı ekranda görüyor ve telefonla okutuyor. Sayfa birkaç saniyede bir bağlantıyı kontrol ediyor, bağlanınca QR kendiliğinden kapanıyor.
  - QR'ın süresi (~40 sn) dolmadan yenisi otomatik isteniyor. Yaklaşık 3 dakika sonra otomatik yenileme duruyor.
  - "Bağlantıyı kes" düğmesi onay istiyor.
  - Yönetici (MANAGER) yalnızca durumu görüyor. STAFF rolü sayfayı ve menü bağlantısını görmüyor.
  - Bağlantı koptuğunda panelin **her sayfasında** kırmızı uyarı çıkıyor: "WhatsApp bağlı değil: müşteriler giriş kodu alamıyor".
- **Panel uçları:** `GET /api/admin/messaging/status` (MANAGER+), `POST /api/admin/messaging/qr` ve `POST /api/admin/messaging/logout` (yalnızca OWNER). Bakım ucunun yanıtına `notificationsFailed`, `notificationsSkipped` ve `driverState` alanları eklendi.
- **Kurulum komutları** (`python -m app.whatsapp`):
  - `connect`: instance oluşturur ve QR kodunu `whatsapp-qr.png` dosyasına yazar.
  - `status`: bağlantı durumunu gösterir.
  - `test <numara>`: deneme mesajı gönderir.
- **Docker:** `docker compose --profile whatsapp up -d`, Evolution API v2.3.6'yı mevcut PostgreSQL ile birlikte başlatıyor (ayrı `evolution_api` şeması, Redis gerekmiyor).
- **Veritabanı:** Migration `0003` ile `scheduled_notification` tablosuna `attempts`, `last_error` ve `next_attempt_at` alanları eklendi.
- **Arayüz metinleri:** Giriş ekranı, SSS ve hatırlatmalar sayfasında "SMS" ifadeleri WhatsApp'a göre güncellendi.

**Doğrulama:** 23 yeni test, sahte bir Evolution sunucusuyla yazıldı; testler gerçek mesaj göndermiyor. Ayrıca lokal Evolution API'ye karşı instance oluşturma, QR üretme, bağlantı durumu okuma ve bağlantı kopukken hızlı hata davranışı elle denendi. Panel sayfası Postgres + Evolution ile çalışan gerçek uygulamada açılıp QR'ın arayüz üzerinden geldiği doğrulandı. **Gerçek bir numarayla uçtan uca gönderim henüz denenmedi**, bunun için QR'ın telefonla okutulması gerekiyor.

### 12. İlk mesajda karşılama

Salonun WhatsApp numarasına **ilk kez** yazan kişiye otomatik bir karşılama mesajı gidiyor. Varsayılan metin:

> Merhaba! 👋 Mesajınız için teşekkürler, *Salon adı* ekibi en kısa sürede size dönüş yapacak.
>
> Online randevu almak için: *site adresi*/randevu

**"İlk mesaj" ne demek:** Salonun o kişiyle daha önce hiç yazışmamış olması. Şu kişilere karşılama **gitmiyor**:
- Sistemin OTP kodu veya hatırlatma gönderdiği müşteriler. Numara, mesaj gitmeden önce "tanıdık" olarak işaretleniyor; müşteri hemen "teşekkürler" diye cevap verse de karşılama almıyor.
- Personelin telefondan yazdığı kişiler.
- Numara bağlanırken telefonda zaten sohbet geçmişi olan kişiler. Yeni sistem kurulduğunda mevcut müşterilerle süren sohbetlere birden karşılama düşmüyor.
- Gruplar, durum (status) paylaşımları ve kanallar.
- 10 dakikadan eski mesajlar. Telefon uzun süre kapalı kalırsa biriken mesajlara toplu karşılama gitmiyor.
- Emoji tepkileri.

**Nasıl çalışıyor:**
- Evolution API gelen ve giden mesajları webhook ile `POST /api/webhooks/evolution` ucuna bildiriyor. İstekler URL'deki gizli anahtarla (`EVOLUTION_WEBHOOK_SECRET`) doğrulanıyor.
- Webhook, backend açılırken ve QR istenirken otomatik kuruluyor.
- Karşılanan kişiler yeni `whatsapp_contact` tablosunda tutuluyor. Tablodaki unique kısıt, Evolution aynı olayı yeniden gönderse ya da iki mesaj aynı anda gelse bile karşılamanın **bir kez** gitmesini garanti ediyor.
- Karşılama arka planda gönderiliyor, webhook yanıtı beklemiyor. Gönderim başarısız olursa yeniden denenmiyor: iki kez gitmesi, hiç gitmemesinden daha kötü.
- WhatsApp bazı kişilerin numarasını gizli bir kimlikle (`@lid`) gösteriyor. Gerçek numara biliniyorsa kişi numarasıyla tanınıyor, böylece aynı kişi iki kez karşılanmıyor. Numara bilinmiyorsa cevap o gizli kimliğe gönderiliyor.

**Panel:** WhatsApp sayfasına "Karşılama mesajı" kartı eklendi. Yönetici ve salon sahibi mesajı açıp kapatabiliyor, metni düzenleyebiliyor (en fazla 1000 karakter, `{salon}` ve `{link}` yer tutucularıyla) ve müşteriye giden hâlini önizleyebiliyor. "Varsayılan metne dön" düğmesi de var.

**Veritabanı:** Migration `0004` ile `whatsapp_contact` tablosu ve `salon` tablosuna `whatsapp_welcome_enabled` ve `whatsapp_welcome_message` alanları eklendi.

**Doğrulama:**
- 19 yeni test yazıldı. Kapsamı: ilk mesaj, tekrar gelen olay, OTP ve hatırlatma alan müşterinin cevabı, personelin yazdığı kişi, `@lid`, gruplar, eski mesajlar, sohbet geçmişi, kapalı ayar, bozuk olay, yetkiler.
- Canlı sistemde de denendi: backend açılışta webhook'u kurdu, Evolution konteyneri webhook ucuna ulaştı, yanlış anahtar 401 ile reddedildi.
- Gerçek bir kişinin yazmasıyla uçtan uca deneme, numara bağlandıktan sonra yapılmalı.

### 13. SQLite kaldırıldı: proje yalnızca PostgreSQL

Proje PostgreSQL'de eksiksiz çalıştığı (tüm testler, seed ve panel uçları doğrulandı) için SQLite'a dair her şey kaldırıldı.

**Kod:**
- `app/db.py`: SQLite'a özel bağlantı ayarları (WAL modu, `BEGIN IMMEDIATE`, `PRAGMA foreign_keys`, `check_same_thread`) silindi. Motor artık yalnızca PostgreSQL için ve `pool_pre_ping` açık: veritabanı yeniden başlatılırsa kopmuş bağlantılar hataya dönüşmüyor.
- `init_db()`: V1'in SQLite veritabanını tanıyıp "uygulanmış" olarak işaretleyen geçiş kodu silindi. Artık yalnızca `alembic upgrade head`.
- `app/config.py`:
  - Varsayılan `DATABASE_URL` lokal PostgreSQL (`aurora@localhost:5432/aurora`).
  - PostgreSQL dışında bir adres verilirse uygulama **her ortamda** açılmıyor.
  - Üretimde varsayılan lokal adresle de açılmıyor; `DATABASE_URL` zorunlu.
- `is_unique_violation`: SQLite için hata mesajı metnine bakan yedek yol silindi, yalnızca PostgreSQL'in `23505` hata kodu kullanılıyor.
- Servislerdeki "SQLite'ta etkisiz", "SQLite'ta yazma kilidi" gibi yorumlar PostgreSQL gerçeğine göre güncellendi.

**Migration'lar:** SQLite'ın sınırlı `ALTER TABLE` desteği için kullanılan `batch_alter_table` blokları (82 işlem) doğrudan PostgreSQL komutlarına çevrildi. Oluşan şema değişmedi. Temiz bir PostgreSQL veritabanında sıfırdan kurulum, `alembic check` (modelle birebir aynı), geri alma ve yeniden kurulumla doğrulandı.

**Testler:**
- SQLite test dosyası (`tests/test.db`) yerine varsayılan olarak Docker'daki `aurora_test` veritabanı kullanılıyor.
- Test başlangıcında tüm tablolar silindiği için, adı `_test` ile bitmeyen bir veritabanı verilirse testler **çalışmayı reddediyor**. Geliştirme veritabanıyla denendi: testler başlamadı, veriye dokunulmadı.
- Yeni testler: SQLite ve MySQL adresleri reddediliyor, üretimde lokal adres kabul edilmiyor.

**Dosyalar:**
- `backend/beauty.db`, `beauty.db-wal` ve `beauty.db-shm` silindi (V1 demo verisi; seed ile yeniden üretilebilir).
- `.gitignore` ve `.dockerignore` içindeki `*.db` kuralları kaldırıldı.
- `.env.example` ve yerel `.env` PostgreSQL'e göre güncellendi.

**Dokümantasyon:** Kök ve backend README'lerindeki SQLite anlatımları (kurulum, mimari şema, "Neden Redis değil" bölümü, test ve ortam değişkeni tabloları) PostgreSQL'e göre yeniden yazıldı. "Sıfır dış bağımlılık" iddiası kaldırıldı; kurulum artık Docker gerektiriyor.

**Bedeli:** Projeyi çalıştırmak ve testleri koşmak için PostgreSQL'in açık olması gerekiyor (`docker compose up -d db`). Karşılığında geliştirme, test ve üretim aynı veritabanında çalışıyor; madde 8'deki gibi SQLite'ın gizlediği hatalar artık geliştirmede görünüyor.

---

## Yeni ortam değişkenleri

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `CRON_SECRET` | boş | Bakım ucu için paylaşılan sır. Üretimde zorunlu, en az 32 karakter |
| `APP_TIMEZONE` | `Europe/Istanbul` | Salonun saat dilimi |
| `CORS_ORIGINS` | geliştirmede `localhost:3000` | Tarayıcı API'ye doğrudan bağlanacaksa izinli origin'ler |
| `TEST_DATABASE_URL` | `…/aurora_test` | Testlerin veritabanı. Adı `_test` ile bitmek zorunda (testler başta tüm tabloları siliyor) |
| `NOTIFICATION_DRIVER` | `console` | `console` veya `evolution`. Tanınmayan değerde uygulama başlamaz |
| `EVOLUTION_API_URL` / `EVOLUTION_API_KEY` / `EVOLUTION_INSTANCE` | boş | `evolution` sürücüsü için zorunlu |
| `WHATSAPP_COUNTRY_CODE` | `90` | Numaralara eklenen ülke kodu |
| `WHATSAPP_SEND_INTERVAL_MS` | `1500` | Kuyruk mesajları arası bekleme |
| `NOTIFICATION_BATCH_SIZE` | `20` | Bir bakım çalıştırmasında en fazla mesaj |
| `EVOLUTION_WEBHOOK_URL` | boş | Evolution'ın backend'e ulaştığı adres (lokal: `http://host.docker.internal:8000`). Boşsa gelen mesajlar alınmaz |
| `EVOLUTION_WEBHOOK_SECRET` | geliştirmede lokal sabit | Webhook doğrulama anahtarı. Üretimde en az 32 karakter |
| `PUBLIC_SITE_URL` | `http://localhost:3000` | Karşılama mesajındaki randevu bağlantısı |

Değişen davranış: `APP_ENV` artık yalnızca `development` ve `test` değerlerinde geliştirme modu. Diğer her değer üretim sayılıyor.

## Yeni bağımlılıklar

`alembic`, `psycopg[binary]`, `tzdata`. `httpx` artık yalnızca test için değil, Evolution API istemcisi için de kullanılıyor. Kurmak için: `pip install -r requirements.txt`.

---

## Lokal geliştirme ortamı

Bu sürümde lokal ortam da PostgreSQL ve WhatsApp ile çalışacak şekilde kuruldu:

- **`backend/.env` oluşturuldu.** Git'e girmiyor. İçeriği:
  - `DATABASE_URL`: Docker'daki PostgreSQL
  - `NOTIFICATION_DRIVER=evolution` ve Evolution bağlantı bilgileri
  - Webhook adresi (`http://host.docker.internal:8000`)
  - `PUBLIC_SITE_URL`
- **Docker'da çalışanlar:** Yalnızca PostgreSQL ve Evolution API (`docker compose --profile whatsapp up -d`). Backend ve arayüz hâlâ bilgisayarda doğrudan çalışıyor (`uvicorn`, `npm run dev`).
- **Veri:** SQLite'taki eski demo verisi PostgreSQL'e taşınmadı; PostgreSQL'e `python -m app.seed` ile demo verisi yüklendi. SQLite dosyaları silindi (madde 13).
- **`docker-compose.yml`:** Evolution servisine `host.docker.internal` eşlemesi eklendi. Windows/Mac'te zaten tanımlı; Linux'ta konteynerin bilgisayardaki backend'e ulaşması için gerekiyor.
- **`.env.example`:** Tüm yeni değişkenler açıklamalarıyla eklendi.
- **`.gitignore`:** `whatsapp-qr.png` eklendi (QR kodu depoya girmesin).
- **Testlerin yalıtımı:** Testler geliştiricinin yerel `.env` dosyasından etkilenmiyor. Mesaj sürücüsü her zaman `console`, Evolution ve webhook ayarları boş. Testler gerçek WhatsApp mesajı göndermiyor.

## Testler

Test sayısı 129'dan 190'a çıktı. Mevcut testler, `datetime.now()` yerine `now_local()` kullanacak ve yeni kurallara (bakım ucunun yetki istemesi, deneme sınırı tablosunun temizlenmesi) uyacak şekilde güncellendi.

| Yeni dosya | Test | Kapsam |
|---|---|---|
| `test_security.py` | 19 | OTP kaba kuvvet koruması, deneme sınırları, bakım ucu yetkisi, üretim yapılandırma doğrulaması, yalnızca PostgreSQL kuralı, saat dilimi |
| `test_messaging.py` | 23 | Evolution istemcisi (sahte sunucu), OTP gönderimi, kuyrukta yeniden deneme, panel QR/bağlantı uçları ve yetkileri |
| `test_whatsapp_welcome.py` | 19 | İlk mesajda karşılama ve "tanıdık kişi" kuralları, panel ayarları |

Çalıştırmak için PostgreSQL'in açık olması yeterli (`docker compose up -d db`), sonra `pytest`. Testler varsayılan olarak `aurora_test` veritabanını kullanıyor; başka bir adres `TEST_DATABASE_URL` ile verilebilir.

## Dokümantasyon ve sürüm

- `backend/README.md` güncellendi: kurulum (Alembic, PostgreSQL), WhatsApp bölümü, üretime alma, ortam değişkenleri, test listesi.
- `README.md` (kök) ve `frontend/README.md` güncellendi: yeni modüller, WhatsApp sayfası, test sayısı.
- Sürüm `2.0.0` olarak güncellendi (`pyproject.toml` ve API başlığı).

---

## Uyumluluk notları (V1'den geçerken)

- **Arayüz:** Mevcut ekranlar V2 backend'iyle değişiklik gerekmeden çalışıyor. V2'de arayüze eklenenler: admin panelindeki WhatsApp sayfası, bağlantı kopukluk uyarısı ve 3 metin güncellemesi. Paneldeki bakım düğmesi artık yalnızca MANAGER ve OWNER rolünde çalışıyor; STAFF rolü 403 alıyor.
- **Müşteri girişi WhatsApp'a bağlı:** `NOTIFICATION_DRIVER=evolution` iken numara bağlanana kadar müşteriler giriş kodu alamaz. Bu geliştirmede de geçerli. Numarayı bağlamadan geliştirmeye devam etmek için `NOTIFICATION_DRIVER=console` kullanılmalı; o zaman kod ekranda görünür.
- **Hata kodu:** Deneme sınırı aşıldığında HTTP `429` ve `RATE_LIMITED` kodu dönüyor. V1'de OTP sınırı `VALIDATION` koduyla dönüyordu.
- **Bakım ucu:** `GET /api/cron/sweep` kaldırıldı. Yalnızca `POST` var ve kimlik doğrulama istiyor.
- **Veritabanı:** V1'in SQLite verisi V2'ye taşınmıyor. V2 boş bir PostgreSQL veritabanında migration'larla kuruluyor, demo verisi `python -m app.seed` ile yükleniyor. V1 yalnızca demo verisiyle kullanıldığı için bu bilinçli bir tercih; gerçek veri olsaydı ayrı bir taşıma betiği gerekirdi.
- **Yeni hata kodu:** `DELIVERY_FAILED` (503 veya 502), kod gönderilemediğinde dönüyor. Arayüz mesajı olduğu gibi gösteriyor.
- **Kuyruk durumları:** `status` alanında yeni bir değer var: `SENDING`. Kayıtlar artık `FAILED` da olabiliyor.

---

## Bu sürümde yapılmayanlar (sıradakiler)

| Konu | Neden hâlâ gerekli |
|---|---|
| **WhatsApp'ın gerçek numarayla denenmesi** | Admin paneli > WhatsApp sayfasından QR okutulup bir müşteri numarasıyla giriş kodu istenerek, başka bir telefondan da salona yazılarak (karşılama) doğrulanmalı |
| Yedek kanal (SMS) | WhatsApp numarası kısıtlanırsa OTP durur. İleride SMS sağlayıcısı yedek sürücü olarak eklenebilir |
| Zamanlayıcı kurulumu | Bakım ucunu 5 dakikada bir çağıracak bir cron işi (sunucuya göre değişir) |
| Yüklenen dosyalar için nesne depolama | Şimdilik Docker volume. Birden fazla sunucuya çıkılırsa S3 veya R2 gerekir |
| Hata takibi ve loglama | Sentry ve yapılandırılmış log. Uygulama kodundaki `print`'ler `logging`'e taşındı, ama loglar hâlâ düz metin ve bir yere toplanmıyor |
| Otomatik veritabanı yedeği | Barındırma sağlayıcısına göre ayarlanacak |
| Oturum token'larını hash'li saklamak | Veritabanı sızıntısında oturumların çalınmasını engeller |
| KVKK ve İYS | Aydınlatma metni, veri silme talebi akışı, kampanya SMS'leri için İYS kaydı |
| Ters proxy IP ayarı | Next.js veya nginx arkasında `FORWARDED_ALLOW_IPS` doğru verilmezse IP sınırları tüm istekleri tek istemci sayar. Numara bazlı sınırlar bundan etkilenmez |
