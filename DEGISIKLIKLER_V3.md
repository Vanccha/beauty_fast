# Aurora V3 — Değişenler

**Tarih:** 1 Ekim 2026
**Kapsam:** Yalnızca arayüz (`frontend/`). Backend'de değişiklik yok.
**Amaç:** Siteyi telefonda ve tablette bir uygulama gibi kullanılabilir hale getirmek (PWA): ana ekrana yüklenebilmesi, kendi penceresinde açılması, bağlantı koptuğunda düzgün bir sayfa göstermesi ve çentikli ekranlarda doğru oturması.

Yeni npm bağımlılığı eklenmedi. `next-pwa` Next 15 ile sorunlu olduğu için Next'in yerleşik manifest desteği ve elle yazılmış küçük bir service worker kullanıldı.

---

## Özet

| # | Değişiklik | Önem |
|---|---|---|
| 1 | Web uygulaması bildirimi (manifest) | 🟢 Yeni özellik |
| 2 | Uygulama simgeleri ve üretim betiği | 🟢 Yeni özellik |
| 3 | Service worker ve önbellek stratejileri | 🟢 Yeni özellik |
| 4 | Çevrimdışı sayfası (`/offline`) | 🟢 Yeni özellik |
| 5 | "Ana ekrana ekle" önerisi (müşteri) ve "Uygulamayı yükle" düğmesi (personel) | 🟢 Yeni özellik |
| 6 | iOS meta etiketleri | 🟢 Yeni özellik |
| 7 | Çentik ve ana ekran çubuğu için güvenli alan boşlukları | 🟠 Mobil düzen |
| 8 | `sw.js` için önbellek başlığı | 🟠 Altyapı |

---

## 🟢 Yeni özellikler

### 1. Web uygulaması bildirimi

**Dosya:** `frontend/src/app/manifest.ts` → `/manifest.webmanifest` olarak servis ediliyor. Next, `<link rel="manifest">` etiketini her sayfaya kendisi ekliyor.

- Uygulama ana ekranda **"Aurora"** adıyla görünüyor ve adres çubuğu olmadan kendi penceresinde açılıyor (`display: standalone`).
- Tema rengi `#77496a` (plum-600), açılış zemini `#faf7f4` (sand-50), tasarım tokenlarıyla aynı.
- **Ekran yönü kilitli değil** (`orientation: any`). Tablette takvim yatay, telefonda randevu akışı dikey kullanılabiliyor.
- Başlangıç adresi `/?source=pwa`. Ziyaretin uygulamadan mı geldiği istenirse ileride ölçülebilir.
- Ana ekran simgesine uzun basınca açılan **kısayollar**:
  - **Randevu al** → `/randevu`
  - **Randevularım** → `/hesabim`
  - **Salon takvimi (personel)** → `/admin/takvim`

### 2. Uygulama simgeleri

**Kaynak:** `frontend/public/icons/icon.svg`. Plum degrade zemin, krem rengi "A" harfi ve küçük bir parıltı. Harf yazı tipine bağlı kalmasın diye yol (path) olarak çizildi.

**Üretim:** `npm run icons` (`frontend/scripts/generate-icons.mjs`). Next ile birlikte gelen `sharp` kullanılıyor; ayrıca kurulum gerekmiyor. PNG'ler depoya ekleniyor, derleme sırasında üretilmiyor.

| Dosya | Boyut | Kullanım |
|---|---|---|
| `icon-192.png`, `icon-512.png` | 192, 512 | Genel simge (yuvarlatılmış köşeli) |
| `maskable-192.png`, `maskable-512.png` | 192, 512 | Android uyarlanabilir simge. Zemin kenardan kenara, içerik %80'lik güvenli alanda |
| `apple-touch-icon.png` | 180 | iOS ana ekranı. Köşeleri iOS kendisi yuvarlıyor, bu yüzden düz kare |
| `icon.svg` | — | Tarayıcı sekmesi simgesi (favicon) |

Simge değiştirilecekse yalnızca `icon.svg` düzenlenip `npm run icons` çalıştırılması yeterli.

### 3. Service worker

**Dosya:** `frontend/public/sw.js`. Bağımlılıksız, yaklaşık 150 satır.

| İstek | Strateji | Neden |
|---|---|---|
| `/api/*` | **Dokunulmuyor**, her zaman ağ | Müsaitlik, slot kilitleri ve oturum canlı olmalı. Bayat bir müsaitlik bilgisi çift rezervasyona yol açar |
| Next istemci gezintisi (RSC) | Dokunulmuyor | Çevrimdışıyken Next tam sayfa yüklemeye düşüyor; o da aşağıdaki gezinti kuralına takılıyor |
| `/_next/static/*` | Önce önbellek | Dosya adları hash'li, içerikleri hiç değişmiyor |
| `/photos`, `/icons`, `/uploads`, `/_next/image`, `/hero.svg` | Önbellekten göster, arka planda tazele | Görseller anında açılıyor. En fazla 120 kayıt tutuluyor, eskiler siliniyor |
| `/`, `/portfolyo`, `/yorumlar` sayfaları | Önce ağ; ağ yoksa önbellekteki kopya | Herkese açık vitrin sayfaları çevrimdışı da görülebiliyor |
| Diğer tüm sayfalar | Önce ağ; ağ yoksa `/offline` | Aşağıya bakınız |

**Gizlilik kararı:** `/hesabim`, `/giris`, `/randevu` ve tüm `/admin` sayfaları **önbelleğe alınmıyor**. Salonda paylaşılan bir tablette bir müşterinin veya personelin bilgileri, oturum kapandıktan sonra önbellekten başkasına görünmesin diye.

**Sürüm yönetimi:** Dosyanın başındaki `VERSION` değeri (`v1`) önbellek adlarının parçası. Değeri artırıp yayınlamak, yeni SW etkinleştiğinde eski önbellekleri siliyor. Yeni SW beklemeden devreye giriyor (`skipWaiting` + `clients.claim`).

**Kayıt:** `frontend/src/components/pwa/ServiceWorkerRegister.tsx`, kök layout'ta.
- Yalnızca **üretim derlemesinde** kaydediliyor ve sayfa yüklendikten sonra devreye giriyor, ilk boyamayı yavaşlatmıyor.
- `npm run dev` altında SW kaydedilmiyor; daha önceden kalmış bir kayıt varsa kaldırılıyor. Aksi halde eski JS parçaları önbellekten gelip sıcak yenilemeyi bozardı.

### 4. Çevrimdışı sayfası

**Dosyalar:** `frontend/src/app/offline/page.tsx`, `retry-button.tsx`

- "Bağlantı yok" başlığı, kısa bir açıklama ve **Tekrar dene** düğmesi.
- Bağlantı geri geldiğinde sayfa kendiliğinden yenileniyor (`online` olayı).
- Bilerek `(shop)` grubunun **dışında**: o kabuk her istekte API'den salon bilgisi çekiyor. Bu sayfada hiçbir veri çağrısı yok, statik üretiliyor ve SW kurulurken önbelleğe alınıyor.

### 5. "Ana ekrana ekle" önerisi

**Dosyalar:** `frontend/src/components/pwa/install.ts`, `InstallBanner.tsx`

**Müşteri arayüzü (`InstallBanner`):**
- Sayfa açıldıktan 3 saniye sonra küçük bir kart çıkıyor. Mobilde alt gezinme çubuğunun hemen üstünde, `md:` üstünde sağ alt köşede.
- **Android / Chrome / Edge / Samsung Internet:** "Yükle" düğmesi tarayıcının kendi yükleme penceresini açıyor.
- **iOS / iPadOS Safari:** Bu tarayıcılar otomatik yükleme penceresini desteklemiyor; kartta "Paylaş → Ana Ekrana Ekle" adımları anlatılıyor. iPadOS kendini masaüstü Safari olarak tanıttığı için dokunmatik nokta sayısıyla ayırt ediliyor.
- Kart kapatılırsa **30 gün** boyunca tekrar gösterilmiyor (`localStorage`).
- Uygulama zaten ana ekrandan açıldıysa hiç görünmüyor.

**Personel paneli (`InstallButton`):**
- Üst bara **Uygulamayı yükle** düğmesi eklendi. Yalnızca tarayıcı yüklemeye izin verdiğinde görünüyor; panelde araya giren bir kart yok.

**Teknik not:** Tarayıcının yükleme olayı (`beforeinstallprompt`) çoğu zaman React hazır olmadan tetikleniyor. Kaçırılmasın diye dinleyici modül yüklenirken kuruluyor ve olay saklanıyor; bileşenler sonradan abone oluyor (`useSyncExternalStore`).

### 6. iOS meta etiketleri

**Dosya:** `frontend/src/app/layout.tsx`

iOS manifestteki simgeleri ve adı okumadığı için ayrıca eklendi:
- `appleWebApp`: ana ekran başlığı "Aurora", durum çubuğu stili `default` (içerik durum çubuğunun altına girmiyor).
- `apple-touch-icon` ve favicon bağlantıları.
- `applicationName: 'Aurora'`.
- `formatDetection: { telephone: false }`: iOS sayfadaki rakamları kendiliğinden telefon bağlantısına çevirmiyor. Gerçek telefon bağlantıları (`tel:`) etkilenmiyor.

---

## 🟠 Mobil düzen

### 7. Güvenli alan boşlukları

Sayfa zaten `viewportFit: cover` ile tüm ekranı kullanıyordu, ama çentik ve ana ekran çubuğu için boşluk bırakılmıyordu. Uygulama kendi penceresinde açılınca bu sorun daha görünür hale gelecekti.

| Yer | Değişiklik |
|---|---|
| Müşteri alt gezinme çubuğu | iPhone ana ekran çubuğu kadar alt iç boşluk (`env(safe-area-inset-bottom)`). Bağlantılar artık çubuğun arkasında kalmıyor |
| Müşteri `main` alt boşluğu | `pb-28` → `7rem + güvenli alan`. İçeriğin son satırı gezinme çubuğunun altında kalmıyor |
| `.page-shell`, `.bleed` | Yatay boşluk `max(1rem, güvenli alan)`. Telefon yan çevrilince içerik çentiğin altına girmiyor |
| Personel paneli `main` | Alt boşluk `max(1rem, güvenli alan)` |
| "Ana ekrana ekle" kartı | Alt gezinme çubuğu ve güvenli alan hesaba katılarak konumlandı |

Masaüstünde ve çentiksiz cihazlarda güvenli alan değeri 0 olduğu için görünüm değişmiyor.

---

## 🟠 Altyapı

### 8. `sw.js` önbellek başlığı

**Dosya:** `frontend/next.config.mjs`

`/sw.js` artık `Cache-Control: no-cache, no-store, must-revalidate` ile servis ediliyor. Böylece yeni bir service worker sürümü tarayıcının HTTP önbelleğinde takılı kalmıyor; kullanıcılar yayından sonraki ilk ziyarette güncel sürümü alıyor.

---

## Dosya listesi

**Yeni:**
- `frontend/src/app/manifest.ts`
- `frontend/src/app/offline/page.tsx`, `frontend/src/app/offline/retry-button.tsx`
- `frontend/src/components/pwa/ServiceWorkerRegister.tsx`
- `frontend/src/components/pwa/install.ts`
- `frontend/src/components/pwa/InstallBanner.tsx`
- `frontend/public/sw.js`
- `frontend/public/icons/` (`icon.svg` ve 5 PNG)
- `frontend/scripts/generate-icons.mjs`

**Değişen:**
- `frontend/src/app/layout.tsx`: iOS/simge meta verisi, SW kaydı
- `frontend/src/app/(shop)/layout.tsx`: güvenli alan boşlukları, "ana ekrana ekle" kartı
- `frontend/src/app/admin/(panel)/layout.tsx`: "Uygulamayı yükle" düğmesi, güvenli alan
- `frontend/src/app/globals.css`: `.page-shell` ve `.bleed` yatay boşlukları
- `frontend/next.config.mjs`: `sw.js` başlıkları
- `frontend/package.json`: `npm run icons` betiği
- `frontend/README.md`: PWA bölümü

## Doğrulama

- `npm run typecheck` ve `npm run build` hatasız. `/offline` ve `/manifest.webmanifest` statik üretiliyor.
- Üretim sunucusunda (`next start`) kontrol edildi:
  - Manifest doğru içerikle servis ediliyor.
  - Tüm simgeler 200 dönüyor.
  - Sayfada manifest, `apple-touch-icon` ve `apple-mobile-web-app-*` etiketleri var.
  - `sw.js` doğru `Cache-Control` ve `Content-Type` başlıklarıyla geliyor.
- **Henüz yapılmadı:** Gerçek bir telefonda veya tablette yükleme ve çevrimdışı davranış denenmedi (aşağıya bakınız).

---

## Uyumluluk notları (V2'den geçerken)

- **Backend:** Değişiklik yok, V2 backend'iyle olduğu gibi çalışıyor.
- **Geliştirme:** `npm run dev` davranışı değişmedi; SW geliştirmede kapalı. PWA'yı denemek için `npm run build && npm start`.
- **HTTPS şartı:** Tarayıcılar yalnızca HTTPS'te (veya `localhost`'ta) uygulama yüklemeye ve SW çalıştırmaya izin veriyor. Telefondan yerel ağ IP'siyle (`http://192.168.x.x:3000`) açıldığında yükleme önerisi çıkmaz ve SW kaydedilmez.
- **Yayın:** Önbellek davranışını değiştiren her yayında `public/sw.js` içindeki `VERSION` artırılmalı.
- **Ters proxy:** Üretimde nginx veya başka bir proxy kullanılırsa `/sw.js` için uzun süreli önbellek başlığı eklenmemeli; Next'in gönderdiği `no-cache` başlığı korunmalı.

---

## Bu sürümde yapılmayanlar (sıradakiler)

| Konu | Neden hâlâ gerekli |
|---|---|
| **Gerçek cihazda deneme** | Android telefon, iPhone ve iPad'de HTTPS üzerinden (ör. ngrok tüneli veya canlı ortam): yükleme, kısayollar, uçak modunda `/offline` ve vitrin sayfaları, çentikli ekranda alt çubuk |
| Lighthouse PWA denetimi | Canlı HTTPS adresinde çalıştırılıp kalan uyarılar giderilmeli |
| Anlık bildirim (Web Push) | Randevu hatırlatmaları şu an WhatsApp'tan gidiyor. iOS 16.4+ ana ekrana eklenmiş uygulamalarda push destekliyor; ileride ikinci kanal olabilir |
| Tablet için panel düzeni | Personel panelinin üst gezinmesi yatay kaydırmalı. Yatay tablette yan menü daha rahat olabilir |
| Yükleme ölçümü | `?source=pwa` parametresi hazır, ama henüz bir analitik aracına bağlanmadı |
| Uygulama içi "yeni sürüm var" bildirimi | Şu an yeni SW sessizce devreye giriyor. Açık kalan sekmede kullanıcıya "Yenile" önerisi gösterilebilir |
