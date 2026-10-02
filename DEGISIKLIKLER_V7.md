# Aurora V7 — Değişenler

**Tarih:** 2 Ekim 2026
**Kapsam:** Arayüz (`frontend/`) ve backend (`backend/`).
**Amaç:** Bildirimlerin gerçekten gitmesini sağlamak, vitrini tek sayfada toplamak ve admin panelini sadeleştirmek:
- Randevuyu alana **"randevunuz oluşturuldu"** WhatsApp mesajı; hatırlatmalar artık **kendiliğinden** gidiyor.
- Ana sayfa kompakt; **Portfolyo, Yorumlar ve Ekibimiz** ana sayfanın bölümleri.
- Admin paneli **akordeon** düzeninde, emojisiz ve premium görünümde.
- Grup randevusunda kişi sayısını değiştirmek daha kolay.

Test sayısı 243'ten 248'e çıktı. Yeni npm veya pip bağımlılığı eklenmedi. Veritabanı değişikliği yok (migration yok).

---

## Özet

| # | Değişiklik | Önem |
|---|---|---|
| 1 | Randevuyu alana WhatsApp onay mesajı | 🟢 Yeni özellik |
| 2 | Hatırlatmaları gönderen arka plan işçisi | 🔴 Hata düzeltmesi |
| 3 | Tek sayfa vitrin: Portfolyo, Yorumlar, Ekibimiz | 🟠 Davranış değişikliği |
| 4 | Yorumlarda yalnızca iyi (4–5 yıldız) yorumlar | 🟠 Davranış değişikliği |
| 5 | Grup randevusunda kişi seçici | 🟢 İyileştirme |
| 6 | Saat düğmelerinde bitiş saati ve fırsat etiketi | 🟢 İyileştirme |
| 7 | Akordeon admin paneli, yapışkan bölüm başlığı | 🟠 Davranış değişikliği |
| 8 | Admin: emojiler kaldırıldı, premium görünüm | 🟢 İyileştirme |
| 9 | Hatırlatma kurallarında JSON yerine okunur parametreler | 🔴 Hata düzeltmesi |
| 10 | Küçük hata düzeltmeleri | 🔴 Hata düzeltmesi |

---

## 🟢 Yeni özellikler

### 1. Randevuyu alana onay mesajı

**Dosyalar:** backend `services/booking_confirmation.py` (yeni), `api/appointments.py`, `api/group_booking.py`, `services/appointment_status.py`

- Önceden yalnızca **başkası adına** alınan randevuda, randevu sahibine bilgilendirme gidiyordu. Randevuyu alan kişiye hiçbir mesaj gitmiyordu.
- Artık randevuyu alan kişiye WhatsApp'tan onay gidiyor:
  > Merhaba {ad}, randevunuz oluşturuldu ✅
  > {tarih} saat {saat} - {hizmetler} · {usta}
  > Randevunuzu görmek veya iptal etmek için: {site}/randevularim
- Başkası adına alınan randevuda satır "{ad} için …" diye başlıyor. **Grup randevusunda** alan kişiye tek bir özet mesaj gidiyor: "2 kişilik grup randevunuz oluşturuldu" ve her kişi ayrı satırda.
- Mesaj doğrudan gönderilmiyor; randevuyla **aynı veritabanı işleminde** bildirim kuyruğuna yazılıyor ve işçi hemen uyandırılıyor (bkz. 2). Bu yüzden:
  - WhatsApp o an kopuksa mesaj kaybolmuyor, bağlantı gelince gidiyor.
  - Randevu isteği WhatsApp yanıtını beklemiyor.
- Randevu, onay gitmeden iptal edilirse onay da iptal ediliyor.
- Randevu sahibine giden bilgilendirme (V6) değişmedi.

---

## 🔴 Hata düzeltmeleri

### 2. Hatırlatmalar hiç gitmiyordu

**Dosyalar:** backend `services/notification_worker.py` (yeni), `main.py`, `config.py`, `.env.example`

- "Yarın randevunuz var" hatırlatmaları kuyruğa yazılıyordu ama kuyruğu boşaltan `/api/cron/sweep` ucunu **otomatik çağıran hiçbir şey yoktu**. Panelden "Kuyruğu işle"ye basılmadıkça mesajlar gitmiyordu.
- Artık backend açıkken arka planda bir işçi kuyruğu **her 60 saniyede** kontrol ediyor. Onay mesajlarında beklemeden tetikleniyor.
- Yeni ayar: `NOTIFICATION_POLL_SECONDS` (varsayılan `60`, `0` = kapalı; o durumda `/api/cron/sweep` dışarıdan tetiklenmeli).
- Birden fazla worker aynı anda çalışabilir; kayıtlar `FOR UPDATE SKIP LOCKED` ile sahiplenildiği için aynı mesaj iki kez gitmez.

| Durum | Ne olur |
|---|---|
| Backend kapalı | Mesaj veritabanında bekler; backend açılınca bir dakika içinde gider |
| WhatsApp kopuk | Gönderim denenmez, deneme hakkı yanmaz; bağlantı gelince gider |
| Gönderim hatası | 5, 10, 20, 40 dk arayla yeniden denenir; 5 başarısız denemede `FAILED` |

### 9. Hatırlatma kurallarında ham JSON

**Dosya:** `admin/(panel)/hatirlatmalar/page.tsx`

- Kural parametreleri `{"mmPerMonth": 12, "toleranceMm": 14}` gibi ham JSON olarak görünüyordu. Artık okunur etiketler var:

| Kural | Önce | Şimdi |
|---|---|---|
| Büyüme | `{"mmPerMonth": 12, "toleranceMm": 14}` | Uzama hızı: 12 mm/ay · Dip toleransı: 14 mm |
| Ürün ömrü | `{"productDays": {"kalici_oje": 21, …}}` | Kalıcı oje: 21 gün · Jel: 28 gün · Klasik oje: 7 gün |
| Mevsimsel | `{"monthFactors": {"7": 1.3, …}}` | Temmuz: ×1,3 (daha seyrek) · Aralık: ×0,85 (daha sık) |

- `FIXED`, `PRODUCT_LIFETIME` gibi formül kodları ve açıklamalardaki `baseDays` gibi alan adları kaldırıldı.
- Bildirim kuyruğunda iptal edilen ve gönderilemeyen mesajlar yanlışlıkla "bekliyor" görünüyordu; artık "iptal", "gönderilemedi", "gönderiliyor" ayrı gösteriliyor.

### 10. Küçük düzeltmeler

- Ana sayfada ekip kartlarındaki puan satırı `<p>` içinde `<div>` olduğu için **hydration hatası** veriyordu (Next'in "3 Issues" uyarısı). Düzeltildi.
- Grup randevusu sayfasında içerik ekran kenarlarına yapışıktı (V6'dan kalma); yan boşluk eklendi.
- `<html>` etiketine `data-scroll-behavior="smooth"` eklendi (Next uyarısı).

---

## 🟠 Davranış değişiklikleri

### 3. Tek sayfa vitrin

**Dosyalar:** `(shop)/layout.tsx`, `site-header.tsx`, `nav-link.tsx`, `use-active-section.ts` (yeni), `(shop)/page.tsx`, `components/marketing/PortfolioGallery.tsx` (yeni), `components/marketing/ReviewsBrowser.tsx` (yeni), `globals.css`

- **Menü:** "Randevu" ve "Randevularım" kaldırıldı; sağdaki **Randevu Al** ve **Randevu Sorgula** zaten var. Menü: Ana Sayfa · Portfolyo · Yorumlar · Ekibimiz. Randevu Sorgula simgesi artık mobil üst barda da görünüyor.
- Portfolyo, Yorumlar ve Ekibimiz ana sayfanın bölümleri (`/#portfolyo`, `/#yorumlar`, `/#ekip`). Menüden tıklayınca sayfa yumuşakça bölüme kayıyor; kaydırırken görünen bölüm menüde aktif işaretleniyor.
- Eski `/portfolyo` ve `/yorumlar` adresleri ana sayfadaki bölümlere yönlendiriliyor (307).
- **Kompakt düzen:** Bölüm boşlukları `py-20 md:py-28` → `py-12 md:py-16`; ilk ekrandaki fotoğraf ekranın %92'si yerine %72'si. Eski "Galeri" bölümü kaldırıldı, yerine gerçek portfolyo geldi.
- **Bölüm sırası:** Kahraman → güven şeridi → kategoriler → imza hizmetler → portfolyo → yorumlar → ekip → kalite sözü → ziyaret → SSS → kapanış.
- **Portfolyo:** Kategori düğmeleri sayfadan çıkmadan filtreliyor; ilk 8 iş, gerisi "Daha fazla göster".

### 4. Yorumlar

- Puan filtreleri (Tüm puanlar / 5 yıldız / 4 yıldız) kaldırıldı. Listede **yalnızca 4–5 yıldızlı** yorumlar gösteriliyor; ilk 6, gerisi "Daha fazla göster". Mobilde yana kaydırılan kartlar, masaüstünde 3 sütun.
- Ortalama puan ve yıldız dağılımı **tüm yorumlardan** hesaplanmaya devam ediyor.
- Bölümdeki "puanlar düzenlenmez veya seçilerek gösterilmez" ifadesi, artık doğru olmadığı için kaldırıldı.
- Eski `/yorumlar` sayfasındaki ustaya göre filtre kaldırıldı.

### 7. Akordeon admin paneli

**Dosyalar:** `admin/(panel)/layout.tsx`, `nav.tsx`, `page.tsx`, `ozet/page.tsx` (yeni), `globals.css`

- Panele girince 10 bölüm alt alta listeleniyor, hiçbiri açık değil. Bir bölüme tıklayınca içeriği **o satırla bir sonraki satır arasında** açılıyor; sayfa açılan bölüme kayıyor.
- Açık satıra tekrar basmak bölümü kapatıyor (`/admin`'e döner).
- **Yapışkan başlık:** Açık bölümde aşağı kaydırınca bölüm başlığı (ör. "Stok" ve ok) üst barın hemen altında sabit kalıyor; kapatmak için yukarı çıkmak gerekmiyor. Üst barın yüksekliği ölçülüp kullanılıyor, bu yüzden mobilde de tam oturuyor.
- Eski açılış ekranı (`/admin`) **Genel Bakış** bölümüne taşındı (`/admin/ozet`).
- Takvim gibi geniş içerik kendi kutusu içinde yana kayıyor; sayfa taşmıyor.

---

## 🟢 İyileştirmeler

### 5. Grup randevusunda kişi seçici

**Dosya:** `randevu/grup/group-flow.tsx`

- Başlığın altında **"Kaç kişi?"** kutusu: büyük **−** / **+** düğmeleri, ortada iri kişi sayısı ve tek dokunuşla **2 · 3 · 4 kişi** seçimi.
- Listenin altında tam genişlikte, kesik çizgili **"Kişi ekle · 2/4 kişi"** kutusu. 4 kişide yerine "Daha kalabalık gruplar için salonu ara" notu çıkıyor.
- Kişi eklenince sayfa yeni karta kayıyor ve imleç ad alanına geçiyor.
- Sayı azaltılırken **önce boş kartlar** çıkarılıyor; yazılmış ad ve telefonlar korunuyor.
- Kartlardaki "Çıkar" düğmesi büyütüldü (44 px dokunma alanı).

### 6. Saat düğmeleri

**Dosyalar:** `randevu/booking-flow.tsx`, `components/engagement/EngagementBadge.tsx`

- "…'e kadar" yazısı kaldırıldı; başlangıç saatinin altında yalnızca bitiş saati var. Boyut 10 px → 13 px.
- "%20 SÜPER FIRSAT" etiketi dar düğmelere sığmıyor, yan yana olanlar birbirine karışıyordu. Saat düğmelerinde artık etiket simgesi + "%20" görünüyor; tam metin fareyle üzerine gelince ve ekran okuyucuda çıkıyor. Diğer yerlerde etiket değişmedi.

### 8. Admin görünümü

**Dosyalar:** `admin/(panel)/*` altındaki tüm bölüm sayfaları, `admin/giris/*`, `globals.css`

- Panelde emoji kalmadı. Menü emojileri ince çizgili simgelerle değişti (Takvim, Müşteriler, Stok, Kampanyalar, Hatırlatmalar, Fırsat Saatleri, Portfolyo, Yorumlar, WhatsApp); sayfa içindeki ⚠️, 🔒, 👁️, ★, ←/→ da simge oldu.
- Üst bar: "Yönetim paneli" etiketi, salon adı sitedeki serif yazı tipiyle, rol "OWNER" yerine **Salon sahibi / Yönetici / Personel**.
- Renkli dolgu etiketler ince çerçeveli oldu; boşluklar sıkılaştı, köşeler 4 px. Bölüm adı akordeon satırında yazdığı için sayfa içi büyük başlıklar kaldırıldı.
- Admin stilleri `.admin-shell` altında tanımlandı; vitrin etkilenmiyor.
- Personel giriş sayfası aynı tarzda yenilendi. Salon adını göstermek için `/api/showcase`'e ek bir istek atıyor.

---

## Doğrulama

- `pytest`: **248 test geçti** (5 yeni: `test_booking_confirmation.py` — onayın kuyruğa yazılıp gitmesi, başkası adına randevuda alana onay, WhatsApp kopukken bekleme, iptalde onayın iptali, grupta tek özet mesaj).
- `npm run typecheck`: hatasız. `npm run build` bu sürümde çalıştırılmadı (geliştirme sunucusu açıktı).
- Ekran görüntüsüyle kontrol (360, 390 ve 1440 px):
  - Ana sayfa: menüden bölümlere kayma, aktif bölüm işareti, yatay taşma yok, konsolda hata yok.
  - Admin: kapalı liste, Hatırlatmalar/Takvim/Müşteriler açık hali, Stok'ta aşağı kaydırınca yapışkan başlık (üst barın altında, 78 px) ve kapatınca satırın görünür kalması.
  - Grup randevusu: + / − / 2·3·4 seçimi, boş kartların önce çıkması, yazılan adın korunması.
  - Saat düğmeleri: 53 düğmede fırsat etiketi taşması yok.

## Bilinmesi gerekenler

- **Sunucu açık kalmalı:** Hatırlatma ve onay mesajları backend ve WhatsApp bağlantısı açıkken gider. Kapalıyken kaybolmazlar ama gecikirler; sistem uzun süre kapalı kalırsa "yarın randevunuz var" hatırlatması geç gidebilir.
- **Şablonlardaki emojiler:** Hatırlatma şablonlarındaki 💅 ve 🙂 müşteriye giden WhatsApp metninin parçası ve veritabanında duruyor; dokunulmadı. Admin'de şablon önizlemesinde görünüyorlar.
- **Henüz yapılmadı:** Gerçek telefonda onay mesajının WhatsApp'tan geldiğinin görülmesi (gerçek numaraya deneme mesajı gönderilmedi; davranış testlerle doğrulandı).
