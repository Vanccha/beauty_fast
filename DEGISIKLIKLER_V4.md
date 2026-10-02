# Aurora V4 — Değişenler

**Tarih:** 2 Ekim 2026
**Kapsam:** Yalnızca arayüz (`frontend/`). Backend'de değişiklik yok.
**Amaç:** V3'te müşteri sitesinde açılıştan 3 saniye sonra çıkan "Ana ekrana ekle" kartının yerine, üst barda her zaman görünen sabit bir **"Uygulamayı yükle"** düğmesi koymak. Kullanıcı yüklemeyi istediği an yapabilsin; açılışta araya giren bir pencere olmasın.

Yeni npm veya pip bağımlılığı eklenmedi. Veritabanı değişikliği yok.

---

## Özet

| # | Değişiklik | Önem |
|---|---|---|
| 1 | Müşteri üst barına sabit "Uygulamayı yükle" düğmesi | 🟢 Yeni özellik |
| 2 | Açılışta çıkan "Ana ekrana ekle" kartı kaldırıldı | 🟠 Davranış değişikliği |
| 3 | `InstallBanner.tsx` → `InstallButton.tsx` (dosya adı) | 🟠 Altyapı |
| 4 | Çerez Politikası: artık kullanılmayan `localStorage` kaydı tablodan çıkarıldı | 🔵 KVKK |
| 5 | `frontend/README.md` PWA bölümü güncellendi | ⚪ Doküman |

---

## 🟢 Yeni özellik

### 1. Üst barda sabit "Uygulamayı yükle" düğmesi

**Dosyalar:** `frontend/src/components/pwa/InstallButton.tsx` (`SiteInstallButton`), `frontend/src/app/(shop)/site-header.tsx`

- Düğme üst barın sağında, **Üye Girişi / Randevu al** düğmelerinin solunda duruyor. Üst bar sayfa kaydırılırken de yerinde kaldığı için düğme her zaman erişilebilir.
- **Mobilde** yalnızca indirme simgesi görünüyor (dar ekranda salon adı ve "Randevu al" düğmesine yer kalsın diye). **`md:` ve üstünde** simge + "Uygulamayı yükle" yazısı. Ekran okuyucular için her iki durumda da `aria-label="Uygulamayı yükle"`.
- Ana sayfanın en tepesinde, fotoğrafın üstündeki saydam üst barda beyaz çerçeveli; kaydırınca ve diğer sayfalarda plum renkli çerçeveli. Diğer üst bar düğmeleriyle aynı geçişi kullanıyor.

**Tarayıcıya göre davranış:**

| Ortam | Düğmeye basınca |
|---|---|
| Android / Chrome / Edge / Samsung Internet (masaüstü dahil) | Tarayıcının kendi yükleme penceresi açılıyor; onay tarayıcıda veriliyor |
| iOS / iPadOS Safari | Düğmenin altında küçük bir kutu açılıyor: "Paylaş → Ana Ekrana Ekle" adımları. Dışına dokunmak, `Esc` veya **Tamam** kapatıyor |

**Düğme şu durumlarda görünmüyor:**
- Uygulama zaten ana ekrandan açılmışsa (bağımsız pencere).
- Tarayıcı yüklemeye izin vermiyorsa (ör. Firefox masaüstü, iOS'ta Safari dışındaki tarayıcılar) veya site HTTPS olmadan açıldıysa (`localhost` hariç).
- Kullanıcı yüklemeyi kabul ettikten sonra (`appinstalled` olayı).

**Teknik not:** Yükleme durumunu tutan ortak kaynak (`install.ts`) değişmedi. `beforeinstallprompt` olayı yine modül yüklenirken yakalanıp saklanıyor; düğme `useCanInstall()` ile abone oluyor. "Zaten yüklü mü" kontrolü hidrasyon uyuşmazlığı olmasın diye ilk boyamadan sonra (`useEffect` içinde) yapılıyor.

---

## 🟠 Davranış değişiklikleri

### 2. "Ana ekrana ekle" kartı kaldırıldı

**Dosya:** `frontend/src/app/(shop)/layout.tsx`

- V3'teki, açılıştan 3 saniye sonra mobilde alt menünün üstünde / masaüstünde sağ altta çıkan kart artık gösterilmiyor. Aynı işlev 1. maddedeki düğmede.
- Kartın "Şimdi değil" bilgisini saklayan `aurora:install-dismissed-at` (`localStorage`, 30 gün) anahtarı artık yazılmıyor ve okunmuyor. Daha önce yazılmış tarayıcılarda kalan değer zararsız; hiçbir yerde kullanılmıyor.

### 3. Dosya adı: `InstallBanner.tsx` → `InstallButton.tsx`

**Dosyalar:** `frontend/src/components/pwa/InstallButton.tsx`, `frontend/src/app/admin/(panel)/layout.tsx`

- Dosyada artık kart yok, yalnızca iki düğme var:
  - `SiteInstallButton` — müşteri üst barı (yeni).
  - `InstallButton` — personel paneli üst barı. **Davranışı değişmedi**; yalnızca import yolu güncellendi.

---

## 🔵 KVKK

### 4. Çerez Politikası güncellendi

**Dosya:** `frontend/src/app/(shop)/cerez-politikasi/page.tsx`

- Tablodaki `aurora:install-dismissed-at` satırı kaldırıldı; site artık bu kaydı tutmuyor. Tabloda oturum çerezleri, `visitor_key` ve uygulama önbelleği kaldı.

---

## ⚪ Doküman

### 5. `frontend/README.md`

- PWA bölümündeki "Yükle önerisi" ifadesi sabit düğme olarak güncellendi; `src/components/pwa/` satırı yeni dosya adını gösteriyor.

---

## Değişen dosyalar

- `frontend/src/components/pwa/InstallButton.tsx` (eski adı `InstallBanner.tsx`)
- `frontend/src/app/(shop)/site-header.tsx`
- `frontend/src/app/(shop)/layout.tsx`
- `frontend/src/app/admin/(panel)/layout.tsx` (yalnızca import yolu)
- `frontend/src/app/(shop)/cerez-politikasi/page.tsx`
- `frontend/README.md`

---

## Doğrulama

- `npm run typecheck` (`tsc --noEmit`): hatasız.
- `npm run dev` altında `/`, `/yorumlar`, `/cerez-politikasi` 200 dönüyor; `/admin` girişe yönlendiriyor (beklenen).
- **Henüz yapılmadı:**
  - Düğmenin tarayıcıda görsel kontrolü (saydam/opak üst bar, mobil genişlik) ve Chrome'da yükleme penceresinin açılması. PWA'nın tam davranışı için `npm run build && npm start` ile denenmeli.
  - iPhone / iPad Safari'de yardım kutusunun açılıp kapanması.
  - Gerçek cihaz denemesi (V3'ten devralınan madde: HTTPS üzerinden Android, iPhone, iPad).
- Projede ESLint yapılandırılmadığı için `npm run lint` çalıştırılmadı.
