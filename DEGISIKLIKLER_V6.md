# Aurora V6 — Değişenler

**Tarih:** 2 Ekim 2026
**Kapsam:** Arayüz (`frontend/`) ve backend (`backend/`).
**Amaç:** Müşteri tarafındaki "üyelik" algısını kaldırmak ve salona birlikte gelenler için randevuyu kolaylaştırmak:
- "Üye Girişi / Hesabım" yerine telefonla **Randevu Sorgula**.
- Kayıtlı numaraya isim tekrar sorulmaması, **İsmimi değiştir**.
- Randevu alırken sayfadan çıkmadan doğrulama.
- **Başkası adına randevu** ve en fazla 4 kişilik **grup randevusu**.

Test sayısı 201'den 243'e çıktı. Yeni npm veya pip bağımlılığı eklenmedi. Veritabanı değişikliği: migration `0006`.

---

## Özet

| # | Değişiklik | Önem |
|---|---|---|
| 1 | Randevu Sorgula (`/randevularim`) | 🟢 Yeni özellik |
| 2 | Kayıtlı isim tekrar sorulmuyor, "İsmimi değiştir" | 🟢 Yeni özellik |
| 3 | Randevu akışında sayfadan çıkmadan doğrulama | 🟢 Yeni özellik |
| 4 | Başkası adına randevu | 🟢 Yeni özellik |
| 5 | Grup randevusu (2–4 kişi, `/randevu/grup`) | 🟢 Yeni özellik |
| 6 | Görünürlük ve iptal kuralları | 🟢 Yeni özellik |
| 7 | Yeni müşterinin adının kaydedilmemesi | 🔴 Hata düzeltmesi |
| 8 | Numaradan isim öğrenmenin engellenmesi | 🔵 KVKK / gizlilik |
| 9 | Müşteri oturumu 180 gün, iptalde hatırlatma da iptal | 🟠 Davranış değişikliği |
| 10 | Veritabanı: migration `0006` | 🟠 Altyapı |

---

## 🟢 Yeni özellikler

### 1. Randevu Sorgula

**Dosyalar:** `frontend/src/app/(shop)/randevularim/*`, `site-header.tsx`, `(shop)/layout.tsx`

- Menüde "Üye Girişi" ve "Hesabım" yok; yerine **Randevu Sorgula** (mobil alt menüde "Randevularım").
- Müşteri numarasını girer, WhatsApp'a gelen kodla doğrular ve randevularını görür. Kod sorgulamada da isteniyor: numara tek başına yeterli olsaydı, başkasının numarasını bilen herkes onun randevularını görüp iptal edebilirdi.
- Sayfa düzeni: "Merhaba, {ad}" → **Yeni randevu al** → yaklaşan randevular (iptal) → geçmiş randevular (yorum) → sadakat seviyesi → albüm → "Kişisel verilerim" (kapalı başlar) → "Bu cihazdan çık".
- `/hesabim` ve `/giris` eski linkler, PWA kısayolları ve yer imleri bozulmasın diye `/randevularim`'e yönlendiriliyor. `/giris?next=...` yönlendirmesindeki `next` korunuyor; yalnızca site içi yollar kabul ediliyor (`lib/safe-next.ts`).

### 2. İsim

**Dosyalar:** `components/auth/PhoneVerify.tsx`, `components/auth/NameEditor.tsx`; backend `PATCH /api/me`

- İsim yalnızca numara ilk kez kullanılıyorsa soruluyor. Kayıtlı numarada "Merhaba, {ad} · **İsmimi değiştir**" satırı çıkıyor; isim yerinde düzenleniyor.
- `PATCH /api/me` `{firstName, lastName?}`: 1–40 karakter, harf, boşluk, `'` ve `-`.
- Kod kutusu `autocomplete="one-time-code"`: telefon gelen kodu klavyenin üstünde öneriyor.

### 3. Akış içinde doğrulama

**Dosya:** `randevu/booking-flow.tsx`

- "Kendim" seçiliyken doğrulanmamış kişi son adımda (Onay) aynı kartın içinde telefon → kod → (yeniyse) ad adımlarını geçiyor; ayrı bir giriş sayfasına gidilmiyor. Tutulan saat ve geri sayım korunuyor.
- Eski `/randevu?resume=1` devam yolu eski linkler için çalışmaya devam ediyor.

### 4. Başkası adına randevu

**Dosyalar:** `booking-flow.tsx`; backend `services/booking_for_other.py`, `api/appointments.py`, `api/slots.py`

- 1. adımda **Kimin için?**: Kendim | Başkası adına | Grup (2–4 kişi).
- "Başkası adına" seçilince önce randevuyu alanın numarası doğrulanıyor, sonra randevu sahibinin yalnızca **ad + telefonu** isteniyor.
- Randevu, randevu sahibinin kaydına yazılıyor (numara kayıtlıysa mevcut kayıt kullanılıyor; yoksa oluşturuluyor). 24 saat hatırlatması da randevu sahibine gidiyor.
- Randevu sahibine WhatsApp'tan yalnızca bilgilendirme mesajı gidiyor, ticari içerik yok:
  > Merhaba {ad}, {alan kişi} senin için {tarih} saat {saat} için {hizmetler} randevusu oluşturdu. Randevunu görmek veya iptal etmek için: {site}/randevularim
- Mesaj gönderilemezse randevu yine oluşuyor; hata yalnızca log'a düşüyor.
- Alerji uyarıları başkası adına alınan randevuda alan kişiye gösterilmiyor (sağlık verisi).
- **Kötüye kullanım limitleri** (24 saat, kayan pencere): bir kişi en fazla 10 başkası adına randevu; bir numaraya en fazla 3. Aşılırsa 429.
- Hizmet linkiyle gelip 1. adımı atlayan kişiye 2. adımda "Kendin için alıyorsun · Başkası adına veya grup için değiştir" satırı gösteriliyor.

### 5. Grup randevusu

**Dosyalar:** `randevu/grup/page.tsx`, `randevu/grup/group-flow.tsx`; backend `api/group_booking.py`, `services/group_booking.py`

- Adımlar: **Kişiler** (2–4; "Ben de katılıyorum" açık başlar) → **Hizmetler** (kişi başı, istenirse usta tercihi) → **Ortak saat** → **Onay**.
- Grup için önce randevuyu alanın numarası doğrulanıyor.
- Sistem herkesin **aynı saatte, farklı ustalarla** başlayabileceği saatleri buluyor. Tek kişilik koltuk gibi ortak kaynaklar çakışmıyor.
- O gün ortak saat yoksa sonraki 7 günden uygun olanları öneriyor ve **Ayrı ayrı randevu al** linkini gösteriyor.
- Saatler **hep birlikte** tutuluyor ve onaylanıyor: biri alınamazsa hiçbiri tutulmuyor. Grup kilit süresi tekil randevunun iki katı (varsayılan 10 dakika).
- Aynı telefon grupta iki kez kullanılamıyor.

**Yeni uç noktalar:**

| Uç nokta | İş |
|---|---|
| `POST /api/availability/group` | Ortak saatler + kişi başı usta/saat/fiyat; boşsa `suggestDates` |
| `POST /api/slots/lock-group` | N saati tek işlemde tutar, `groupId` döner |
| `DELETE /api/slots/lock-group/{groupId}` | Grubun tuttuğu saatleri bırakır |
| `POST /api/appointments/group` | Tümünü tek işlemde oluşturur |
| `POST /api/appointments/group/{groupId}/cancel` | Grubu toplu iptal (yalnızca alan kişi) |

### 6. Görünürlük ve iptal

| Kim | Ne görür | Neyi iptal edebilir |
|---|---|---|
| Randevuyu alan kişi | Aldığı tüm randevular, "Kimin için: {ad}" etiketiyle; grup randevuları bir arada | Hepsini; tek tek ya da "Grubu iptal et" |
| Randevu sahibi (kendi numarasıyla) | Yalnızca kendi randevusu | Kendi randevusu |

Yorum yazma, tasarım görseli yükleme ve albüm yalnızca randevu sahibine açık.

---

## 🔴 Hata düzeltmesi

### 7. Yeni müşterinin adı kaydedilmiyordu

Eski giriş formu isim adımında doğrulama isteğini aynı (kullanılmış) kodla tekrar gönderiyordu; istek sessizce başarısız oluyor, müşteri "Yeni Üye" olarak kalıyordu. Artık doğrulama isimsiz yapılıyor, isim ayrıca `PATCH /api/me` ile kaydediliyor.

---

## 🔵 KVKK / gizlilik

### 8. Numaradan isim öğrenme engellendi

Başkası adına randevu alan kişi, listede randevu sahibinin sistemde **kayıtlı gerçek adını** görüyordu. Rastgele numaralar girerek insanların adını öğrenmek mümkündü. Artık alan kişiye her zaman **kendi yazdığı isim** gösteriliyor (`appointment.beneficiary_label`); gerçek isim yalnızca randevu sahibine görünüyor. WhatsApp mesajındaki hitap da yazılan isimle yapılıyor. Testle korunuyor.

---

## 🟠 Davranış değişiklikleri

### 9. Oturum ve hatırlatma

- Müşteri oturumu 30 günden **180 güne** çıktı. 150 günün altına inince kullanımda yeniden 180 güne uzuyor (her istekte veritabanına yazmamak için). Personel oturumu değişmedi (7 gün).
- Randevu iptal edilince bekleyen 24 saat hatırlatması da iptal ediliyor (önceden kuyrukta kalıyordu).
- Başkası adına oluşturulan bir kayıt, kişi kendi numarasıyla ilk doğrulamayı yaptığında normal müşteri kaydına dönüşüyor.

### 10. Migration `0006_baskasi_adina_ve_grup_randevu`

| Tablo | Alan | Not |
|---|---|---|
| `appointment` | `booked_by_customer_id` | Randevuyu alan kişi; FK, silinince NULL |
| `appointment` | `booking_group_id` | Grup kimliği |
| `appointment` | `beneficiary_label` | Alan kişinin yazdığı isim |
| `slot_lock` | `beneficiary_customer_id`, `group_id`, `service_ids` | Başkası adına ve grup kilitleri |

`downgrade` simetrik; 0005'e geri dönüş denendi.

---

## Doğrulama

- `pytest`: **243 test geçti** (42 yeni: `test_book_for_other.py`, `test_group_booking.py`).
- `npm run typecheck` ve `npm run build`: hatasız.
- Uçtan uca API denemesi: yeni numara doğrulandı ve isim kaydedildi → Pazar için ortak saat yok, başka günler önerildi → 3 kişiye aynı saatte 3 farklı usta bulundu → tek işlemde tutuldu ve onaylandı → iki kişiye bilgilendirme mesajı oluştu → alan kişi 3 randevuyu yazdığı isimlerle, arkadaş yalnızca kendininkini gördü → grup iptali 3 randevuyu iptal etti.
- Ekran görüntüsüyle kontrol: Randevu Sorgula, randevu akışı 1. adım, grup sayfası (390px). Alt menüde `/randevularim`'de "Randevu" sekmesinin de aktif görünmesi düzeltildi.

## Bilinmesi gerekenler

- **WhatsApp:** Doğrulama kodu ve bilgilendirme mesajları Evolution API üzerinden gidiyor. `.env`'de `NOTIFICATION_DRIVER=evolution` seçiliyken servis çalışmıyorsa kod gönderilemez (503). Geliştirmede `NOTIFICATION_DRIVER=console` ile mesajlar log'a yazılır; demo kodu `DEV_OTP_CODE=123456`.
- **Henüz yapılmadı:** Gerçek telefonda WhatsApp ile uçtan uca deneme; grup ve başkası adına akışlarının tarayıcıda tıklanarak denenmesi (API düzeyinde ve ekran görüntüsüyle kontrol edildi).
