# Aurora V3 — Değişenler

**Tarih:** 1 Ekim 2026
**Kapsam:** Arayüz (`frontend/`) ve backend (`backend/`). Backend değişiklikleri yalnızca KVKK maddelerinde (9–14); PWA maddeleri (1–8) yalnızca arayüzde.
**Amaç:**
- Siteyi telefonda ve tablette bir uygulama gibi kullanılabilir hale getirmek (PWA): ana ekrana yüklenebilmesi, kendi penceresinde açılması, bağlantı koptuğunda düzgün bir sayfa göstermesi ve çentikli ekranlarda doğru oturması.
- KVKK uyumu: aydınlatma, açık rıza ve çerez metinleri; ileti onayı ve sağlık verisi rızasının sistemde toplanması; müşterinin verisini indirme ve hesabını silme hakkı; saklama sürelerinin otomatik uygulanması.

> ⚠️ **Canlıya çıkmadan önce:** KVKK metinlerindeki şirket unvanı, MERSİS/vergi bilgisi, e-posta ve KEP adresi **temsilidir**. Satış yapılan salona göre `frontend/src/lib/legal.ts` dosyasından güncellenecek ve metinler hukukçuya gözden geçirtilecek. Ayrıntılı liste: "Canlıya çıkmadan önce: KVKK" bölümü.

Test sayısı 190'dan 201'e çıktı. Yeni npm veya pip bağımlılığı eklenmedi. `next-pwa` Next 15 ile sorunlu olduğu için Next'in yerleşik manifest desteği ve elle yazılmış küçük bir service worker kullanıldı.

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
| 9 | KVKK Aydınlatma Metni, Açık Rıza Metinleri, Çerez Politikası sayfaları | 🔵 KVKK |
| 10 | Ticari ileti onayı: giriş formunda isteğe bağlı kutu, onaysız müşteriye tekrar hatırlatması gitmez | 🔵 KVKK |
| 11 | Alerji (sağlık verisi) kaydında açık rıza zorunluluğu | 🔵 KVKK |
| 12 | Hesabım → "Gizlilik ve verilerim": onay yönetimi, verilerimi indir, hesabımı sil | 🔵 KVKK |
| 13 | Saklama sürelerinin bakım işinde otomatik uygulanması | 🔵 KVKK |
| 14 | Veritabanı: migration `0005` (rıza ve anonimleştirme alanları) | 🔵 KVKK |

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

**Sürüm yönetimi:** Dosyanın başındaki `VERSION` değeri (şu an `v2`) önbellek adlarının parçası. Değeri artırıp yayınlamak, yeni SW etkinleştiğinde eski önbellekleri siliyor. Yeni SW beklemeden devreye giriyor (`skipWaiting` + `clients.claim`).

**Kayıt:** `frontend/src/components/pwa/ServiceWorkerRegister.tsx`, kök layout'ta.
- Yalnızca **üretim derlemesinde** kaydediliyor ve sayfa yüklendikten sonra devreye giriyor, ilk boyamayı yavaşlatmıyor.
- `npm run dev` altında SW kaydedilmiyor; daha önceden kalmış bir kayıt varsa kaldırılıyor. Aksi halde eski JS parçaları önbellekten gelip sıcak yenilemeyi bozardı.

### 4. Çevrimdışı sayfası

**Dosyalar:** `frontend/src/app/offline/page.tsx`, `retry-button.tsx`

- "Bağlantı yok" başlığı, kısa bir açıklama ve **Tekrar dene** düğmesi.
- Bağlantı geri geldiğinde sayfa kendiliğinden yenileniyor (`online` olayı).
- Bilerek `(shop)` grubunun **dışında**: o kabuk her istekte API'den salon bilgisi çekiyor. Bu sayfada hiçbir veri çağrısı yok, statik üretiliyor ve SW kurulurken önbelleğe alınıyor.
- SW kurulurken sayfanın yalnızca HTML'i değil, kullandığı JS ve CSS dosyaları da önbelleğe alınıyor. Dosya adları her derlemede değiştiği için liste elle tutulmuyor; önbelleğe alınan HTML'in içinden okunuyor.

> **Bilgisayarda denemede bulunan hata (düzeltildi):** İlk sürümde (`v1`) yalnızca `/offline` HTML'i önbelleğe alınıyordu. Çevrimdışıyken sayfanın JS dosyası yüklenemediği için "Bağlantı yok" yerine `Application error: a client-side exception` (`ChunkLoadError`) görünüyordu. Düzeltmeyle birlikte `VERSION` `v2`'ye yükseltildi; daha önce `v1` kurulmuş tarayıcılar bir sonraki ziyarette yeni sürümü alıp eski önbellekleri siliyor.

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

## 🔵 KVKK

Önce sistemin gerçekte işlediği kişisel veriler `backend/app/models.py` üzerinden çıkarıldı; metinler ve kurallar bu envantere göre yazıldı. Hassas bulgular:
- **Alerji kaydı:** KVKK m.6'ya göre özel nitelikli sağlık verisi; yalnızca açık rızayla işlenebilir. Önceden rıza alınmıyordu.
- **"Bakım zamanın geldi" tekrar hatırlatmaları:** 6563 sayılı Kanun'a göre ticari ileti; önceden onay istenmiyordu.
- **Salonlar arası risk havuzu:** Telefonun hash'i ve gelme/gelmeme bilgisi paylaşılıyor.
- **Eksik haklar:** Müşterinin verisini indirmesinin veya hesabını silmesinin bir yolu yoktu.

### 9. Metin sayfaları

| Sayfa | İçerik |
|---|---|
| `/kvkk` | Aydınlatma Metni (KVKK m.10): veri sorumlusu, veri kategorileri / amaç / hukuki sebep tablosu, toplama yöntemi, aktarımlar (WhatsApp yurt dışı, barındırma, risk havuzu), saklama süreleri, m.11 hakları, başvuru yöntemi |
| `/acik-riza` | İki **ayrı** rıza metni: `#ticari-ileti` ve `#saglik`. İkisi de isteğe bağlı; randevu almanın şartı değil |
| `/cerez-politikasi` | Kullanılan tüm çerezler ve tarayıcı depoları (oturum, `visitor_key`, PWA önbelleği, localStorage) |

- **Yer:** `frontend/src/app/(shop)/kvkk`, `acik-riza`, `cerez-politikasi`. Ortak kabuk `src/components/legal/LegalDocument.tsx`.
- **Salon bilgileri:** Salon adı, adres ve telefon sistemden (`/api/showcase`) geliyor. Yasal kimlik bilgileri `src/lib/legal.ts` dosyasında tek yerde.
- **Temsili uyarı:** `legal.ts` içinde `isRepresentative: true` olduğu sürece her metnin başında sarı bir "Temsili metindir" uyarısı görünüyor. Gerçek bilgiler girilince `false` yapılmalı.
- **Bağlantılar:** Alt bilgiye üç metnin bağlantısı eklendi. Giriş formunda, numara girilirken aydınlatma metni bağlantısı gösteriliyor (veri toplanmadan önce).
- **Çerez onay penceresi yok, bilinçli olarak:** Sitede yalnızca zorunlu çerezler var; analitik veya reklam çerezi yok. İleride böyle bir araç eklenirse önce onay penceresi eklenmeli.

### 10. Ticari ileti onayı

- **Giriş formu:** "Bakım zamanı hatırlatmaları ve kampanyalar için WhatsApp ile ileti almak istiyorum" kutusu eklendi. İsteğe bağlı ve **varsayılan olarak işaretsiz**.
- **Kayıt:** İşaretlenirse `customer.marketing_consent_at` alanına onay zamanı yazılıyor. Kutu işaretlenmeden tekrar giriş yapmak mevcut onayı geri almıyor.
- **Kuyruğa alma:** Randevu tamamlanınca üretilen tekrar hatırlatması (`repeat:` anahtarlı) yalnızca onaylı müşteri için kuyruğa giriyor.
- **Gönderim anında kontrol:** Onay kuyruğa alındıktan sonra geri alınmış olabilir. Bu durumda mesaj gönderilmiyor, kayıt `CANCELLED` oluyor.
- **Geri alma:** Onay geri alınınca bekleyen tekrar hatırlatmaları hemen iptal ediliyor.
- **Randevu öncesi hatırlatma** (`pre:` anahtarlı) hizmet bildirimidir; onaydan bağımsız gönderilmeye devam ediyor.
- **Panel:** Müşteri kartında "İleti onayı var / yok" rozeti görünüyor.

### 11. Alerji kaydında açık rıza

- Müşterinin **ilk** alerji kaydında personel "Müşteriye sağlık verisi açık rıza metnini okuttum ve açık rıza verdi" kutusunu işaretlemek zorunda. Kutu işaretlenmeden **Kaydet** pasif.
- Sunucu da aynı kuralı uyguluyor (`CONSENT_REQUIRED`). Rıza zamanı `customer.health_consent_at` alanına yazılıyor; sonraki kayıtlarda kutu tekrar sorulmuyor.
- Müşteri rızasını Hesabım'dan geri alırsa tüm alerji kayıtları **kalıcı olarak siliniyor**. Müşteri rızayı kendisi "verildi" yapamıyor; rıza salonda alınıyor.
- **Mevcut veriler:** Migration, daha önce alerji kaydı olan müşterilerin rıza tarihini ilk alerji kaydının tarihiyle dolduruyor. Gerçek bir salonda bu müşterilerden yazılı rıza ayrıca alınmalı.

### 12. Hesabım → "Gizlilik ve verilerim"

Hesabım sayfasının altına eklendi (`/hesabim#gizlilik`). Dört işlem:

| İşlem | Davranış | Uç nokta |
|---|---|---|
| İleti onayı aç/kapat | Anahtar düğme; onay tarihi gösteriliyor | `PATCH /api/me/privacy` |
| Alerji rızasını geri al | Onay adımından sonra alerji kayıtları silinir | `PATCH /api/me/privacy` |
| Verilerimi indir | Profil, rızalar, randevular, alerjiler, paylaşılan notlar, fotoğraflar, yorumlar, puan geçmişi (JSON) | `GET /api/me/export` |
| Hesabımı sil | Onay adımından sonra hesap anonimleştirilir ve oturum kapanır | `DELETE /api/me` |

**Hesap silme satırı silmiyor, anonimleştiriyor.** Randevu tablosu müşteriye `CASCADE` ile bağlı olduğu için satır silinseydi salonun ciro ve doluluk geçmişi de silinirdi.
- **Silinenler:** alerjiler, personel notları, fotoğraflar (diskteki dosyalar dahil), tasarım referansları, yorumlar, bekleyen bildirimler, kampanya hakları, oturumlar, doğrulama kodları ve randevu notları.
- **Boşaltılanlar:** ad, telefon, e-posta, doğum tarihi ve rızalar. Ad "Silinmiş üye" oluyor, telefon `X000000026` gibi bir yer tutucuya dönüşüyor.
- **Kalanlar:** Randevu satırları kimliksiz istatistik olarak kalıyor.
- **Engel:** Yaklaşan randevusu olan müşteri hesabını silemiyor; önce iptal etmesi isteniyor.
- **Sonrası:** Silinen müşteri panel listesinde görünmüyor. Aynı numarayla yeniden kayıt olunabiliyor; yeni ve boş bir hesap açılıyor.

**Bilinçli karar:** Personelin `STAFF_ONLY` notları self-servis dökümde yer almıyor. Bunlar da kişisel veri; müşteri yazılı başvuru yaparsa salon tarafından ayrıca verilmeli. Hukukçuya sorulacaklar listesinde.

### 13. Saklama süreleri

`POST /api/cron/sweep` bakım işi artık şunları da siliyor (`backend/app/services/privacy.py`):

| Kayıt | Süre |
|---|---|
| Saat görüntüleme sayaçları (`slot_view_event`) | 30 gün |
| Gönderilmiş / başarısız / iptal bildirimler | 180 gün (bekleyenlere dokunulmuyor) |
| Risk havuzu kayıtları (`phone_risk_event`) | 12 ay (risk skoru son 6 ayı kullanıyor) |

Doğrulama kodları ve oturumlar zaten süreleri dolunca siliniyordu. Metinlerdeki süreler `frontend/src/lib/legal.ts` → `RETENTION` içinde. Backend'de bir süre değişirse orası da güncellenmeli.

### 14. Veritabanı

Migration `0005_kvkk_riza_ve_anonimlestirme`: `customer` tablosuna `marketing_consent_at`, `health_consent_at`, `anonymized_at` alanları eklendi. Geliştirme veritabanına uygulandı; `alembic check` şema farkı bulmuyor.

### Testler (KVKK)

`backend/tests/test_kvkk.py`, 11 test:
- İleti onayının yalnızca açıkça verilince kaydedilmesi.
- Onay geri alınınca yalnızca ticari iletilerin iptali.
- Onaysız müşteriye tekrar hatırlatmasının kuyruğa alınmaması ve gönderilmemesi.
- Alerji kaydında rıza zorunluluğu; rıza geri alınınca alerjilerin silinmesi.
- Dökümde gizli notların bulunmaması.
- Yaklaşan randevuda silmenin engellenmesi; anonimleştirmenin kapsamı ve oturumun kapanması.
- Silinen müşterinin panelde görünmemesi.
- Saklama süresi temizliğinin yalnızca süresi dolanları silmesi.

`tests/conftest.py`'de test temizliğine `SlotViewEvent` eklendi.

---

## Canlıya çıkmadan önce: KVKK

Bu sürümdeki KVKK metinleri **temsili** ve hukuki görüş değil. Satış yapılan salona göre aşağıdakiler revize edilecek:

| Yapılacak | Ayrıntı |
|---|---|
| **Veri sorumlusu bilgileri** | `frontend/src/lib/legal.ts`: ticari unvan (şahıs işletmesiyse ad soyad), MERSİS no, vergi dairesi/no, KVKK başvuru e-postası, KEP adresi, güncelleme tarihi. Sonra `isRepresentative: false` |
| **Hukukçu incelemesi** | Üç metnin tamamı. Özellikle aşağıdaki maddeler |
| **WhatsApp ve yurt dışı aktarım (m.9)** | Mesajlar WhatsApp (Meta) sunucularından geçiyor. Hangi aktarım mekanizmasının (standart sözleşme vb.) kullanılacağı belirlenmeli. Evolution API resmî WhatsApp Business API değil; bu da ayrıca değerlendirilmeli |
| **Salonlar arası risk havuzu** | Hash'lenmiş telefon diğer salonlarla ortak havuzda kullanılıyor; hukuki sebep "meşru menfaat" olarak yazıldı. Tek salonlu kurulumda havuz fiilen salon içinde kalır. Çok salonlu kullanımda ayrıca değerlendirilmeli |
| **Doğum tarihi** | "Meşru menfaat (doğum günü indirimi)" olarak yazıldı; açık rıza gerekip gerekmediği netleştirilmeli |
| **Personel gizli notları** | Self-servis dökümde yok; yazılı başvuruda verilmeleri gerekip gerekmediği netleştirilmeli |
| **İYS kaydı** | Ticari ileti gönderen işletme İleti Yönetim Sistemi'ne kayıt olmalı, onaylar İYS'ye bildirilmeli. Onay kanıtının onay bittikten sonra 3 yıl saklanması gerekir; şu an geri alınan onayın tarihi tutulmuyor (İYS'ye geçişle birlikte ele alınmalı) |
| **VERBİS** | Salonun VERBİS kayıt yükümlülüğü olup olmadığı (çalışan sayısı / ciro / özel nitelikli veri işleme) kontrol edilmeli |
| **Mevcut alerji kayıtları** | Migration öncesi girilmiş alerjiler için müşterilerden yazılı rıza alınmalı |
| **Mevcut müşterilerin ileti onayı** | Mevcut müşterilerde onay yok; bu sürümle birlikte onlara tekrar hatırlatması gitmez. İsteyenler Hesabım'dan ya da bir sonraki girişte onay verebilir |
| **Personel bilgilendirmesi** | Çalışanlara (personel verisi: ad, telefon, fotoğraf) ayrı bir çalışan aydınlatma metni verilmeli. Bu sürümde yalnızca müşteri metinleri var |
| **Veri işleme sözleşmeleri** | Barındırma sağlayıcısı ile veri işleyen sözleşmesi |

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

**KVKK — yeni:**
- `backend/app/services/privacy.py`, `backend/app/api/privacy.py`
- `backend/migrations/versions/0005_kvkk_riza_ve_anonimlestirme.py`
- `backend/tests/test_kvkk.py`
- `frontend/src/app/(shop)/kvkk/page.tsx`, `acik-riza/page.tsx`, `cerez-politikasi/page.tsx`
- `frontend/src/app/(shop)/hesabim/privacy-panel.tsx`
- `frontend/src/components/legal/LegalDocument.tsx`, `frontend/src/lib/legal.ts`

**KVKK — değişen:**
- `backend/app/models.py`: `Customer` rıza ve anonimleştirme alanları
- `backend/app/main.py`: gizlilik router'ı
- `backend/app/api/auth.py`: girişte ileti onayı
- `backend/app/api/admin.py`: alerji kaydında rıza kapısı, müşteri kartında rıza durumu
- `backend/app/api/public.py`: bakım işine saklama süresi temizliği
- `backend/app/services/appointment_status.py`: tekrar hatırlatması yalnızca onaylıya
- `backend/app/services/notifications.py`: gönderim anında onay kontrolü
- `backend/app/services/customer_profile.py`: rıza alanları, silinen müşteriler listede yok
- `backend/tests/conftest.py`: `SlotViewEvent` temizliği
- `frontend/src/app/(shop)/giris/login-form.tsx`: ileti onay kutusu, aydınlatma bağlantısı
- `frontend/src/app/(shop)/hesabim/page.tsx`: gizlilik bölümü
- `frontend/src/app/(shop)/layout.tsx`: alt bilgide yasal metin bağlantıları
- `frontend/src/app/admin/(panel)/musteriler/[id]/page.tsx`, `crm-editors.tsx`: rıza kutusu ve rozeti
- `frontend/src/app/globals.css`: `.legal` metin stilleri

## Doğrulama

- `npm run typecheck` ve `npm run build` hatasız. `/offline` ve `/manifest.webmanifest` statik üretiliyor.
- Üretim sunucusunda (`next start`) kontrol edildi:
  - Manifest doğru içerikle servis ediliyor.
  - Tüm simgeler 200 dönüyor.
  - Sayfada manifest, `apple-touch-icon` ve `apple-mobile-web-app-*` etiketleri var.
  - `sw.js` doğru `Cache-Control` ve `Content-Type` başlıklarıyla geliyor.
- **Bilgisayarda Chrome ile denendi:**
  - Service worker etkinleşti ve sayfayı kontrol ediyor.
  - Chrome sayfayı yüklenebilir buldu ve "Ana ekrana ekle" kartı göründü.
  - Sunucu durdurulunca `/randevu` yerine "Bağlantı yok" sayfası açıldı; `/` ve `/portfolyo` önbellekten açıldı.
  - `v1` → `v2` geçişinde eski önbellekler silindi.
- **Bilinen sınır:** Çevrimdışı vitrin sayfalarında yalnızca daha önce ekranda görülmüş fotoğraflar çıkar; hiç kaydırılıp görülmemiş görseller önbellekte olmaz.
- **Henüz yapılmadı:** Gerçek bir telefonda veya tablette yükleme ve çevrimdışı davranış denenmedi (aşağıya bakınız).

**KVKK:**
- Backend testlerinin tamamı geçiyor (201).
- `npm run typecheck` ve `npm run build` hatasız. Migration geliştirme veritabanına uygulandı; `alembic check` şema farkı bulmuyor.
- **Tarayıcıda uçtan uca denendi:**
  - Giriş formunda ileti onay kutusu işaretlenerek yeni bir test müşterisi açıldı; onay Hesabım'da tarihiyle göründü.
  - Anahtar düğmeyle onay geri alındı; veri dökümü ucu çağrılıp içeriği kontrol edildi (İndir düğmesine tıklanmadı).
  - Hesap silindi: oturum kapandı, ana sayfaya dönüldü, veritabanında kayıt "Silinmiş üye" olarak anonimleşti.
  - Panelde rızası olmayan müşteride alerji formunun rıza kutusu çıktı; kutu işaretlenmeden **Kaydet** pasif kaldı.
- **Fark edilen, bu sürümde düzeltilmeyen hata (KVKK'dan bağımsız, önceden vardı):** Yeni üye girişinde ad adımı adı kaydetmiyor; müşteri "Yeni Üye" adıyla kalıyor. Sebep: ad, doğrulama kodu ikinci kez gönderilerek kaydediliyor, ama kod ilk denemede tüketildiği için bu istek başarısız oluyor.

---

## Uyumluluk notları (V2'den geçerken)

- **Backend ve veritabanı:** KVKK için yeni migration var. Güncellemeden sonra `cd backend` ve `alembic upgrade head` çalıştırılmalı (Docker imajı açılışta bunu kendisi yapıyor).
- **Tekrar hatırlatmaları:** Artık yalnızca ileti onayı veren müşterilere gidiyor. Mevcut müşterilerde onay olmadığı için, onlar onay verene kadar bu mesajlar gönderilmeyecek. Kuyrukta bekleyenler gönderim anında iptal edilecek.
- **Alerji kaydı:** Panelde ilk alerji kaydında rıza kutusu zorunlu. API'yi doğrudan kullanan bir istemci varsa `consentConfirmed: true` göndermeli, aksi halde `CONSENT_REQUIRED` hatası alır.
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
