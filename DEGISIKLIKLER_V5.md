# Aurora V5 — Değişenler

**Tarih:** 2 Ekim 2026
**Kapsam:** Yalnızca arayüz (`frontend/`). Backend'de değişiklik yok.
**Amaç:** Müşteri arayüzünü bir güzellik salonunun premium hissini verecek şekilde yenilemek. Menüdeki emojiler, sistem fontları ve her yerde aynı yuvarlak kartlar "hazır şablon" görüntüsü veriyordu. Bunların yerine tutarlı bir renk paleti, tipografi ve bileşen sistemi getirildi.

Yeni npm bağımlılığı: `lucide-react` (ikonlar). Veritabanı değişikliği yok. Veri çekme, form ve iş mantığına dokunulmadı; değişiklikler görünümle sınırlı.

---

## Özet

| # | Değişiklik | Önem |
|---|---|---|
| 1 | "Kil & Şarap" renk paleti (krem, bordo, pirinç) ve durum renkleri | 🟢 Tasarım |
| 2 | Fraunces (başlık) + Manrope (gövde) yazı tipleri | 🟢 Tasarım |
| 3 | Buton, chip, input, uyarı kutusu ve kart sistemi | 🟢 Tasarım |
| 4 | Header, mobil/tablet alt menü ve footer yenilendi | 🟢 Tasarım |
| 5 | Müşteri arayüzünde emojiler yerine çizgi ikonlar | 🟢 Tasarım |
| 6 | Tüm müşteri sayfaları yeni dile çekildi | 🟢 Tasarım |
| 7 | Admin paneli renk ve buton görünümünü ortak temadan alıyor | 🟠 Davranış değişikliği |

---

## Tasarım kararlarının dayanağı

Değişikliklerden önce bir araştırma yapıldı: görsel algı ve güven üzerine kanıta dayalı bulgular ve premium güzellik/spa markalarının (Aesop, Aman, Le Labo vb.) ve randevu sistemlerinin (Fresha, Treatwell) ortak kalıpları incelendi.

- **Uygulanan, iyi desteklenen bulgular:** kullanıcı bir sayfanın kalitesine çok kısa sürede karar veriyor; estetik bulunan arayüz daha kolay kullanılır algılanıyor; gerçek fotoğraf, iletişim bilgisi ve tutarlı tipografi güveni artırıyor; renk markanın kişiliğiyle uyumlu olmalı.
- **Bilerek uygulanmayan mitler:** "kadınlar pembe/pastel sever", "altın lüks demektir", "mavi güven verir". Palet bu klişelere göre değil, sıcak ve sakin bir marka kişiliğine göre seçildi.
- **Kaldırılan "hazır şablon" işaretleri:** menüde emoji, her şeyin `rounded-2xl` ve gölgeli olması, sistem fontu, degrade lekeler.

---

## 🟢 Tasarım

### 1. Renk paleti

**Dosya:** `frontend/src/app/globals.css` (`@theme`)

Mevcut token adları (`sand-*`, `plum-*`, `ink-*`) korundu, değerleri değişti. Böylece eski sınıfları kullanan her yer (admin dahil) yeni paleti kendiliğinden aldı.

| Rol | Token | Değer |
|---|---|---|
| Zemin (krem) | `sand-50` | `#F7F3EE` |
| Çizgi | `sand-200` | `#E4DCD2` |
| Metin | `ink-900` | `#221E1B` |
| İkincil metin | `ink-500` | `#6B625A` |
| Vurgu (bordo) | `plum-600` / hover `plum-700` | `#6E2B3A` / `#571F2C` |
| Detay (pirinç) | `brass-500` | `#B08D57` (yalnızca süs; metin için `brass-700`) |

- Yeni token grupları: `brass-*`, `success-*`, `danger-*`, `warning-*`. Müşteri arayüzünde Tailwind'in hazır `rose/amber/emerald` renkleri bunlarla değiştirildi.
- Kontrast: metin/zemin 14.9:1, bordo üstünde beyaz 10.1:1 (WCAG AA üstü).
- `manifest.ts` ve `layout.tsx` tema rengi `#6E2B3A`.

### 2. Yazı tipleri

**Dosyalar:** `frontend/src/app/layout.tsx`, `globals.css`

- Başlıklar **Fraunces**, gövde **Manrope**. İkisi de `latin-ext` alt kümesiyle yükleniyor (ş, ğ, ı, İ doğru görünüyor).
- `next/font` ile derleme sırasında projeye gömülüyor; çalışma anında Google'a istek yok, çevrimdışı/PWA davranışı bozulmuyor.

### 3. Bileşen sistemi

**Dosya:** `globals.css` (`@layer components`)

- **Butonlar:** 2px köşe, büyük harf, geniş harf aralığı, 48px yükseklik. Türler: `.btn-primary`, `.btn-secondary` (çerçeveli), `.btn-ghost`, `.btn-link` (alt çizgisi soldan dolar), `.btn-light` / `.btn-outline-light` (fotoğraf üstü), `.btn-danger`; boyut: `.btn-sm`.
- **Chip:** `.chip`, seçili hali `.chip-active` (koyu) ve `.chip-primary` (randevu seçimlerinde bordo). Filtreler, gün ve saat seçimleri bunu kullanıyor.
- **Input:** `.field` 48px, ince çerçeve, odakta koyu çizgi.
- **Uyarı kutuları:** `.alert-success / -danger / -warning / -info`, solda çizgi ikon.
- **Kart:** gölge yok, 1px çizgi, 4px köşe.
- **Hareket:** 150–250 ms geçişler, `.reveal` giriş animasyonu; "hareketi azalt" tercihi olan kullanıcılarda animasyon kapanıyor.
- Zeminde çok hafif kâğıt dokusu (%3).

### 4. İskelet

**Dosyalar:** `site-header.tsx`, `nav-link.tsx`, `(shop)/layout.tsx`

- **Header:** "A" kutusu kalktı; serif "Aurora Beauty Studio" yazısı. Menü linkleri büyük harf ve geniş aralıklı, aktif sayfa pirinç alt çizgiyle. Tam menü 1024px ve üstünde; altında alt menü kullanılıyor.
- **Alt menü:** mobil ve tablette (1024px altı). İkonlar çizgi ikon; aktif sekmenin üstünde pirinç çizgi.
- **Footer:** koyu zemin, içerik ve linkler aynı. Mobilde alt menünün footer'ı örtmemesi için alt boşluk footer'a taşındı.

### 5. Emoji yerine ikon

- Alt menü 🏠 📅 ✨ 👤 → `House`, `CalendarDays`, `Images`, `UserRound`.
- Ana sayfa özellik listesi, hesap sayfası 🔗, randevu ✅ ⚠️, rozetler 👀 ⏳, metin içi ★ ve ← → işaretleri lucide ikonlarına çevrildi.
- **Kategori ikonları:** Kategorilerin emojileri (💅 💇 👁 🧖) backend verisinden geliyor. Veriye dokunmadan, müşteri arayüzünde kategori adına (slug) göre çizgi ikon gösteren `CategoryIcon` bileşeni eklendi (`tirnak` → el, `sac` → makas, `kas-kirpik` → göz, `cilt` → çiçek; tanımsız kategori → parıltı). Admin tarafında emojiler olduğu gibi duruyor.

### 6. Sayfalar

- **Ana sayfa:** fotoğraflı hero, büyük serif başlık; hizmetler sağda süre ve fiyat olan satır listesi; yorumlar italik alıntı biçiminde.
- **Randevu akışı:** ince adım göstergesi, chip'li gün/saat seçimi, uyarılar ikonlu kutularda. Akış mantığına dokunulmadı.
- **Hesap, giriş, portfolyo, yorumlar, KVKK metinleri, çevrimdışı sayfası:** aynı dile çekildi. KVKK metinleri rahat okunacak satır genişliğinde (68 karakter).

---

## 🟠 Davranış değişikliği

### 7. Admin paneli

Admin aynı `globals.css` dosyasını kullandığı için yeni renkleri ve buton görünümünü (büyük harf, 48px) aldı. Admin dosyalarında değişiklik yapılmadı; menüdeki emojiler duruyor. Dar tablolarda butonlar biraz iri durabilir.

---

## Doğrulama

- `npm run typecheck` ve `npm run build`: hatasız. Sayfa JS boyutlarında anlamlı artış yok (ikonlar yalnızca kullanıldıkları sayfalara yükleniyor).
- Ekran görüntüsüyle kontrol: ana sayfa (1024 / 1440px), randevu, giriş, portfolyo, yorumlar (masaüstü ve 390px), admin girişi.
- Riskli dosyalarda (randevu akışı, OTP girişi, KVKK silme/indirme, randevu iptali) farkın yalnızca `className`, ikon ve sarmalayıcı etiketlerden oluştuğu kontrol edildi.
- **Henüz yapılmadı:** Admin panelinin iç sayfaları (takvim, müşteriler) giriş gerektirdiği için görsel olarak kontrol edilmedi.
