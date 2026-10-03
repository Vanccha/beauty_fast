# Aurora V8 — Değişenler

**Tarih:** 3 Ekim 2026
**Kapsam:** Arayüz (`frontend/`) ve backend (`backend/`).
**Amaç:** Görünümü yumuşatmak ve randevu akışını sadeleştirmek. Bunun yanında KVKK ve sağlık beyanı onayları, pazarlama otomasyonları, tutarlı indirim kuralı, admin paneli için kutu menü ve push bildirimleri eklendi.

Test sayısı 248'den 419'a çıktı. Yeni pip bağımlılığı var: `pywebpush`. Yeni npm bağımlılığı yok. **6 yeni migration** var: 0008, 0009, 0010, 0011, 0012 ve 0013.

---

## Özet

| # | Değişiklik | Önem |
|---|---|---|
| 1 | Yumuşak tasarım: yuvarlak butonlar, bordo seçimler, açık footer | 🟢 İyileştirme |
| 2 | "Usta" → "Personel" | 🟠 Davranış değişikliği |
| 3 | Sade randevu akışı ve her adımda "Önceki adım" | 🟢 İyileştirme |
| 4 | Dolu saatler kırmızı, müsait saatler yeşil | 🟢 Yeni özellik |
| 5 | KVKK aydınlatma onayı, sağlık beyanı ve isteğe bağlı alerji kaydı | 🟢 Yeni özellik |
| 6 | Randevu iptalinde WhatsApp mesajı | 🟢 Yeni özellik |
| 7 | Admin girişinde "Beni hatırla" | 🟢 Yeni özellik |
| 8 | Portfolyo yönetimi (düzenle, gizle, sırala) | 🟢 Yeni özellik |
| 9 | Admin: kutu menü, karşılama mesajı, müşteri geçmişi, Türkçe durumlar | 🟠 Davranış değişikliği |
| 10 | Slogan, davetkâr buton metinleri, WhatsApp butonu | 🟢 İyileştirme |
| 11 | Ziyaret sonrası mesaj (puanlama, Google, Instagram) | 🟢 Yeni özellik |
| 12 | Hizmete göre tekrar randevu daveti ve RET ile çıkış | 🟢 Yeni özellik |
| 13 | Sabit indirim: hafta içi 12:00'den önce %10 | 🟠 Davranış değişikliği |
| 14 | Admin push bildirimleri ve WhatsApp bağlantı denetimi | 🟢 Yeni özellik |
| 15 | Sadakat seviyesi küçük rozet | 🟢 İyileştirme |
| 16 | Admin takviminden tam manuel randevu yönetimi | 🟢 Yeni özellik |
| 17 | Kapora (IBAN ile ön ödeme), son 1 saatte iptal yasağı, iade takibi | 🟢 Yeni özellik |
| 18 | Hata düzeltmeleri | 🔴 Hata düzeltmesi |

---

## 🟢 Görünüm ve randevu akışı

### 1. Yumuşak tasarım

**Dosyalar:** `globals.css`, `(shop)/layout.tsx`, `PortfolioGallery.tsx`, `booking-flow.tsx`, `group-flow.tsx`, `site-header.tsx`, `InstallButton.tsx`

- **Butonlar:** Hepsi yuvarlak uçlu (`rounded-full`), biraz daha küçük ve yumuşak. İkincil butonlar siyah değil bordo çerçeveli.
- **Filtre ve seçim kutuları:** Siyah seçili hal kaldırıldı. Seçili kutu artık üst menüdeki gibi açık bordo zeminli ve bordo yazılı.
- **Kartlar:** Hizmet ve personel kartları, portfolyo görselleri ve form alanları yuvarlak köşeli.
- **Footer:** Siyah zemin yerine kumdan açık bordoya geçen yumuşak bir zemin geldi. En altta **"Created by BecTech"** yazısı var.

### 2. Usta → Personel

- Müşterinin gördüğü yerlerde ve admin panelinde "usta" kelimesi "personel" oldu. Bu, randevu akışını, grup randevusunu, ana sayfayı, Randevularım sayfasını, admin portfolyo ve takvim sayfalarını kapsıyor.
- Kod yorumlarına ve hukuki metinlere (KVKK, açık rıza) dokunulmadı.

### 3. Sade randevu akışı

- **Kaldırılan yazılar:**
  - "Birden fazla seçebilirsin… tek kesintisiz blok…"
  - "Ara saate sığar"
  - "Yalnızca seçtiğin… personeller listelenir"
  - "tüm personel taranır"
- Takvimdeki renkli zaman çubuğu ve açıklaması kaldırıldı. Yerine tek satırlık toplam süre ve tutar geldi.
- "Bu tarih için uygun saat bulunamadı" uyarısı artık ikonlu, dikkat çekici bir kutuda.
- 2. adımdan itibaren her adımın üstünde **"‹ Önceki adım · …"** butonu var. Grup randevusunda da var. Tutulan saat doğru şekilde serbest bırakılıyor.

### 4. Dolu ve müsait saatler

**Dosyalar:** `core/availability.py`, `services/availability.py`, `booking-flow.tsx`

- `POST /api/availability` yanıtında her personel için yeni bir `busySlots: [{startMin, label}]` alanı var. Eklenen bir alan olduğu için mevcut kullanımları bozmuyor.
- **Müsait saatler:** Açık yeşil.
- **Dolu saatler:** Açık kırmızı, üstü çizili, altında "Dolu" yazıyor ve seçilemiyor.
- Grid'in üstünde küçük bir "● Müsait ● Dolu" açıklaması var.
- Grup randevusu ortak saatleri listelediği için orada personel bazında bir saat ızgarası yok. Bu yüzden grup randevusu değişmedi.

---

## 🟢 Onaylar ve WhatsApp

### 5. KVKK ve sağlık beyanı

**Dosyalar:** `api/appointments.py`, `api/group_booking.py`, `services/appointment.py`, `services/privacy.py`, `components/booking/ConsentChecks.tsx` (yeni), `kvkk/page.tsx`, migration `0008`

- Telefon doğrulaması aynen duruyor. Son adıma iki **zorunlu** kutu eklendi:
  - "KVKK Aydınlatma Metni'ni okudum." Aydınlatma bir rıza değil, bilgilendirmedir; bu yüzden "kabul ediyorum" yazılmadı.
  - Sağlık beyanı: alerji, hamilelik, cilt hassasiyeti gibi durumları personele bildireceğine dair beyan. Sağlık verisi saklanmıyor, yalnızca beyanın verildiği an kaydediliyor.
- **İsteğe bağlı alerji kaydı:** Alerji bilgisi, ayrı bir açık rıza kutusuyla kaydediliyor (KVKK m.6). Randevu buna bağlı değil. Başkası adına ve grup randevusunda bu alan gösterilmiyor.
- **Veritabanı:** Randevuya `privacy_notice_ack_at` ve `health_declaration_at` alanları eklendi. Veri dışa aktarımı ve anonimleştirme bu alanları kapsıyor.
- **Hata kodları:** `PRIVACY_NOTICE_REQUIRED`, `HEALTH_DECLARATION_REQUIRED`, `CONSENT_REQUIRED`. Bu hatalarda tutulan saat silinmiyor.

### 6. İptal mesajı

**Dosyalar:** `services/booking_cancellation.py` (yeni), `services/appointment_status.py`, `api/appointments.py`

- Müşteri de iptal etse salon da iptal etse randevu sahibine şu mesaj gidiyor: "Merhaba {ad}, {tarih} saat {saat} - {hizmetler} randevunuz iptal edildi. Yeni randevu almak için: {site}/randevu"
- Başkası adına alınan randevuda randevuyu alan kişiye de ayrı bir mesaj gidiyor.
- Grup iptalinde randevuyu alana tek bir özet mesaj gidiyor, her kişiye ayrıca kendi mesajı gidiyor.
- Aynı randevu iki kez iptal edilirse tek mesaj gidiyor. Gelmedi (NO_SHOW) durumunda mesaj gitmiyor.

### 7. Beni hatırla

- `POST /api/auth/staff/login` artık `rememberMe` alanını alıyor.
- **İşaretliyse:** Oturum 30 gün sürüyor.
- **İşaretsizse:** Oturum en fazla 12 saat sürüyor ve tarayıcı kapanınca kapanıyor.

---

## 🟠 Admin paneli

### 8. Portfolyo yönetimi

**Dosyalar:** `api/admin.py`, `services/portfolio.py`, `uploads.py`, `portfolyo/portfolio-manager.tsx`

- **Yeni uç noktalar:** `PATCH /api/admin/portfolio/{id}` ile başlık, açıklama, kategori, personel, yayın durumu ve görsel değiştirilebiliyor. `POST /api/admin/portfolio/reorder` ile sıralama yapılıyor.
- **Arayüz:** Düzenle, Gizle/Yayınla, yukarı/aşağı sıralama ve sayfa içi onaylı silme.
- Gizli işler sitede görünmüyor. Silinen ya da değiştirilen işin eski görsel dosyası da siliniyor.

### 9. Kutu menü ve diğer düzenlemeler

- **Kutu menü:** Akordeon menü kaldırıldı. `/admin` açılınca büyük kutular görünüyor: mobilde 2 sütun var ve 10 bölüm ekranı dolduruyor, geniş ekranda 3–5 sütun var. Bir bölüme girince en üstte sabit duran **"‹ Menü"** çubuğuyla geri dönülüyor.
- **Karşılama mesajı:** Kapalı geliyor. Sayfada önizleme ve **Düzenle** butonu var, mevcut mesaj Düzenle'ye basınca açılıyor.
- **Randevu durumları Türkçe:** Bekliyor, Onaylandı, Tamamlandı, İptal edildi, Gelmedi (`lib/appointment-status.ts`). Bu etiketler admin panelinde ve Randevularım sayfasında kullanılıyor.
- **Müşteri randevu geçmişi:** Her randevu tek satırda hizmet ve tarih olarak görünüyor, tıklayınca detay açılıyor. Önce son 8 randevu görünüyor, kalanı "Tümünü göster" ile açılıyor.
- **Notlar:** "Usta notları" başlığı "Notlar" oldu ve açıklama yazısı kaldırıldı.
- **WhatsApp sayfası:** "Dikkat edilmesi gerekenler" bölümü kaldırıldı.

---

## 🟢 Pazarlama

### 10. Slogan ve metinler

- **Slogan:** Ana ekranın başlığı **"Kendinize ayırdığınız / en güzel saat."**
- **Butonlar:** "Size uygun saati bulalım" ve "Saatinizi seçin".
- **Onay ekranı:** "Sizi bekliyoruz, {ad}".
- **WhatsApp butonu:** Sağ altta sabit bir buton (`(shop)/whatsapp-fab.tsx`). Randevu sayfalarında gizleniyor.

### 11. Ziyaret sonrası mesaj

**Dosyalar:** `services/post_visit.py` (yeni), `whatsapp/post-visit-settings.tsx` (yeni), migration `0009`

- Randevu Tamamlandı olunca, varsayılan olarak 2 saat sonra teşekkür mesajı gidiyor. Mesajda puanlama, Google yorum ve Instagram linkleri var.
- **Varsayılan olarak kapalı.** Google ve Instagram linkleri şimdilik temsili: `ORNEK-GOOGLE-YORUM-LINKI` ve `ornek_salon`. Gerçek linkler girilene kadar panel uyarı gösteriyor.
- Metin, gecikme süresi ve linkler Admin → WhatsApp sayfasından düzenleniyor.

### 12. Tekrar randevu daveti

**Dosyalar:** `services/rebooking.py` (yeni), `hatirlatmalar/rebooking-settings.tsx` (yeni), `services/whatsapp_inbound.py`, `services/notifications.py`

- **Ayar ekranı:** Admin → Hatırlatmalar → "Yenileme daveti". Her hizmet için açma/kapama, "X gün / hafta / ay" ve mesaj metni ayarlanıyor. Örnek veride Saç Boyası 90 gün, Manikür 14 gün.
- **Gönderim kuralları:**
  - Randevudaki her hizmete bakılıyor, müşteriye en yakın tarihli tek bir davet gidiyor.
  - Müşteri bu arada yeniden randevu aldıysa davet gitmiyor.
  - Yalnızca **ticari ileti onayı veren** müşterilere gidiyor (ETK/İYS).
- **Çıkış:** Mesajın sonunda "RET yazabilirsiniz" satırı var. Gelen "RET" mesajı onayı kaldırıyor. "İPTAL" kelimesi bilerek çıkış sayılmıyor.

---

## 🟠 İndirim kuralı

### 13. Sabit hafta içi sabah indirimi

**Dosyalar:** `core/opportunity.py`, `services/availability.py`, `api/appointments.py`, `api/group_booking.py`, `api/slots.py`, `firsat-saatleri/discount-settings.tsx` (yeni), migration `0010`

- **Eski kural:** Doluluğa göre her saatte değişen %5–%25 indirim.
- **Yeni kural:** **Hafta içi 12:00'den önce başlayan randevulara sabit %10.** Hafta sonu ve öğleden sonra indirim yok.
- **Ayarlar:** Admin → Fırsat Saatleri sayfasında açma/kapama, oran (%5–%30), bitiş saati (10:00–13:00) ve günler seçiliyor. Bu ayarları yalnızca yöneticiler değiştirebiliyor.
- **Tek hesap:** Saat listesi, tek kişilik randevu ve grup randevusu aynı fonksiyonu (`fixed_window_discount`) kullanıyor. İndirim sunucuda yeniden hesaplanıyor, müşterinin gönderdiği oran dikkate alınmıyor.
- Doluluk haritası artık yalnızca bilgi amaçlı, fiyatı etkilemiyor.

---

## 🟢 Bildirimler

### 14. Admin push bildirimleri

**Dosyalar:** `api/push.py`, `services/push.py`, `services/whatsapp_health.py`, `tools/vapid.py` (hepsi yeni), `public/sw.js`, `components/pwa/PushBell.tsx` (yeni), migration `0011`

- Admin panelinin üst barında 🔔 zil var. Bildirim izni yalnızca butona basınca isteniyor. Hangi bildirimlerin geleceği her cihaz için ayrı seçilebiliyor. Test bildirimi gönderilebiliyor.
- **Bildirim türleri:**
  - Yeni randevu (alerji varsa "⚠ Alerji uyarısı" ekleniyor)
  - İptal
  - 3 yıldız ve altı yeni yorum
  - Bir ürünün kritik stok seviyesine ilk düşmesi
- **WhatsApp denetimi:** Bağlantı 5 dakikada bir kontrol ediliyor (`WHATSAPP_HEALTH_SECONDS`). Üst üste 2 başarısız kontrolde "koptu" bildirimi gidiyor, düzelince "yeniden kuruldu" gidiyor. Kopukluk sürerse 6 saatte bir hatırlatma gidiyor.
- **Kim neyi alıyor:** Salon sahibi ve yöneticiler bildirimlerin hepsini alıyor. Personel yalnızca kendisine atanan randevuların bildirimlerini alıyor.
- **Anahtarlar:** `python -m app.tools.vapid` ile oluşturuluyor; `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` ve `VAPID_SUBJECT` değerleri `.env`'e yazılıyor. Geliştirme ortamında anahtar yoksa `backend/.vapid-dev.json` dosyası otomatik oluşturuluyor; bu dosya gitignore'da.

---

## 🟢 Sadakat

### 15. Sadakat seviyesi rozeti

**Dosya:** `components/engagement/TierProgress.tsx`

- Randevularım sayfasındaki büyük "BRONZ" kartı küçük bir rozete dönüştü: ikonlu, yuvarlak, "Bronz üye" yazıyor. Eskiden ekranda Türkçe ad değil, ham seviye kodu görünüyordu.
- **Seviye renkleri:** Bronz bakır tonunda, Gümüş gri, Altın altın sarısı, VIP bordo ve taç ikonlu.
- Puan sağda küçük yazıyor. Altında ince yuvarlak bir ilerleme çubuğu ve "X seviyesine N puan kaldı" yazısı var.
- "≈ X TL" değer yazısı kaldırıldı, çünkü puanlar şu an hiçbir yerde harcanamıyor.
- **Mevcut sadakat mantığı (değişmedi):**
  - **Puan:** Her 10 TL için 1 puan veriliyor. Bu puan üç çarpanla değişiyor: gelme sıklığı (×0,90–×1,25), indirimli saat (%10 indirimle ×1,2) ve seviye (×1,00–×1,20).
  - **Seviyeler:** 0 puanla Bronz, 500 puanla Gümüş, 1500 puanla Altın, 4000 puanla VIP.
  - **Erime:** Müşteri 90 gün gelmezse puanları her 6 ayda bir yarıya iniyor.

---

## 🟢 Manuel randevu yönetimi

### 16. Admin takviminden tam kontrol

**Dosyalar:** `services/manual_booking.py` (yeni), `api/admin.py`, `services/appointment_status.py`, `services/appointment.py`, `models.py`, `takvim/appointment-sheet.tsx` (yeni), `takvim/calendar-board.tsx`, `takvim/page.tsx`, migration `0012`

- **Önceki durum:**
  - Randevular sürüklenerek taşınabiliyordu.
  - Tamamlandı / Gelmedi / İptal butonları vardı ama yalnızca onaylanmış randevularda çalışıyordu.
  - Elle randevu ekleme ve düzenleme yoktu.
- **Elle ekleme** (`POST /api/admin/appointments`):
  - Takvimde "+ Randevu ekle" butonu var, mobilde ayrıca sabit buton var. Boş bir saate dokunmak da personeli ve saati dolu getiriyor.
  - Kayıtlı müşteri ad ya da telefonla aranabiliyor (`GET /api/admin/customers/search`). Ad ve telefonla yeni müşteri eklenebiliyor, yurtdışı numaraları da kabul ediliyor.
  - Süre ve fiyat online randevuyla aynı yöntemle hesaplanıyor. İndirim kuralı uygulanıyor, fiyat elle değiştirilebiliyor. Canlı önizleme `POST /api/admin/appointments/preview` üzerinden geliyor.
  - "Müşteriye WhatsApp onayı gönder" seçeneği var. Randevu varsayılan olarak Onaylandı durumunda oluşuyor, istenirse Bekliyor seçilebiliyor.
  - Seçilen saat doluysa `SLOT_CONFLICT` hatası ve Türkçe sebep dönüyor. Yöneticiler "Yine de ekle" (`force`) ile araya randevu sıkıştırabiliyor. Personel yalnızca kendi adına ekleyebiliyor ve `force` kullanamıyor.
  - Randevuya `source` (`ONLINE` / `ADMIN`) ve `created_by_staff_id` alanları eklendi. Takvimde "Panelden eklendi" etiketi görünüyor.
- **Düzenleme** (`PATCH /api/admin/appointments/{id}`):
  - Hizmet, personel, tarih, saat, fiyat ve not değiştirilebiliyor. Takvim hücreleri aynı işlemde yeniden yazılıyor ve 24 saat önceki hatırlatma yeni saate taşınıyor.
  - İstenirse müşteriye "Merhaba {ad}, randevunuz güncellendi: …" mesajı gidiyor.
  - Son durumdaki randevular (Tamamlandı, İptal edildi, Gelmedi) önce geri alınmadan düzenlenemiyor.
- **Durumlar:**
  - Bekleyen randevular da onaylanabiliyor ve iptal edilebiliyor.
  - İptalde "Müşteriye iptal mesajı gönder" seçeneği var.
- **Geri al** (`POST /api/admin/appointments/{id}/revert`, yalnızca yöneticiler): Randevu yeniden Onaylandı durumuna dönüyor ve önceki durumun etkileri tersine çevriliyor.
  - **Tamamlandı:** Sadakat puanı ters kayıtla düşülüyor, stok geri ekleniyor. Risk kaydı siliniyor, bekleyen tekrar daveti ve ziyaret sonrası mesaj iptal ediliyor.
  - **İptal edildi / Gelmedi:** Risk kaydı siliniyor ve bekleyen iptal mesajı geri çekiliyor. Saat hâlâ boşsa randevu yerine konuyor; doluysa 409 dönüyor.
- **Sürükleyerek taşıma:** Bırakınca "Randevu taşındı · Müşteriye bildir" çubuğu çıkıyor (`POST /api/admin/appointments/{id}/notify-update`). 24 saat önceki hatırlatma artık yeni saate göre güncelleniyor.

---

## 🟢 Kapora

### 17. Kapora, iptal kuralı ve iade takibi

**Dosyalar:** `services/deposit.py`, `services/deposit_watch.py` (yeni), `api/admin.py`, `api/appointments.py`, `api/group_booking.py`, `api/slots.py`, `api/public.py`, `api/push.py`, `services/appointment_status.py`, `services/booking_cancellation.py`, `services/manual_booking.py`, `services/notifications.py`, `lib/deposit.ts`, `components/booking/DepositNotice.tsx`, `whatsapp/deposit-settings.tsx`, `takvim/deposit-lists.tsx` (yeni), migration `0013`

- **Ayarlar** (Admin → WhatsApp → Kapora, yalnızca yöneticiler):
  - **Varsayılan olarak kapalı.** Açmak için IBAN ve alıcı adı zorunlu. IBAN mod-97 ile doğrulanıyor.
  - Yüzde (%20), en az tutar (100 TL), banka, onay süresi (60 dk) ve WhatsApp mesaj metni ayarlanıyor.
  - Mesaj metninde şu yer tutucular kullanılabiliyor: `{ad} {tarih} {saat} {hizmetler} {tutar} {kapora} {iban} {alici} {banka} {aciklama}`.
- **Tutar:** Kapora `max(tutar × yüzde, en az tutar)` olarak hesaplanıyor, randevu tutarını geçmiyor ve tam TL'ye yuvarlanıyor.
- **Durumlar:**

| Durum | Olay | Sonuç |
|---|---|---|
| Kapora kapalı | Online randevu | Onaylandı (eskisi gibi) |
| Kapora açık | Online randevu / panelde "Kapora iste" | **Kapora bekleniyor** (saat dolu görünür) |
| Kapora bekleniyor | Yönetici "Kapora ödendi" | Onaylandı + Ödendi |
| Kapora bekleniyor | İptal ("Kapora yatırılmadı") | İptal edildi, özel mesaj gider |
| Ödendi | Müşteri iptali (≥ 1 saat önce) | İade bekliyor (48 saat süre) |
| Ödendi | Salon iptali | İade bekliyor; yönetici isterse "Kapora yanar" seçebilir |
| Ödendi | Gelmedi | Kapora yandı |
| İade bekliyor | Yönetici "Kapora iade edildi" | İade edildi |

- **Mesajlar:**
  - **Kapora isteği:** Normal "randevunuz oluşturuldu" mesajının yerine gidiyor. Tutar, IBAN, alıcı, açıklama kodu (ör. "R1234 Ayşe Y.") ve iptal kuralı içeriyor.
  - **Kapora ulaştı:** "Merhaba {ad}, kaporanız ulaştı. {tarih} saat {saat} randevunuz kesinleşti. Görüşmek üzere!"
  - **Kapora yatırılmadığı için iptal:** "… randevunuz için kapora yatırılmadığından randevunuz iptal edilmiştir. Yeni randevu için: {site}/randevu"
  - **İptal mesajına ek satır** (kapora ödenmişse): "Kaporanız 48 saat içinde tarafınıza gönderilecektir."
  - **İade edildi:** "Merhaba {ad}, {kapora} tutarındaki kaporanız iade edilmiştir."
- **İptal kuralı:** Müşteri, randevuya **1 saatten az kala** online iptal edemiyor (`CANCEL_TOO_LATE`). Kapora kapalı olsa da bu kural geçerli. Ekranda iptal butonu yerine "Randevuya 1 saatten az kaldığı için iptal edilemez. Kapora iade edilmez." açıklaması çıkıyor. Salon her zaman iptal edebiliyor.
- **Admine bildirimler** (push, "Kapora" tercihi):
  - Kapora süresinde onaylanmazsa: "Kapora bekleniyor … 1 saattir onaylanmadı". Her randevu için bir kez gidiyor, otomatik iptal yok.
  - İade işaretlenmezse: süre dolmadan 24 saat önce, süre dolunca ve sonra her gün hatırlatma gidiyor.
- **Takvimde:**
  - "Kapora bekleyenler" ve "İade bekleyenler" listeleri, süresi geçenler vurgulu.
  - Detay panelinde Kapora ödendi, İade edildi, Kapora mesajını tekrar gönder ve iptal sebebi seçenekleri.
  - Yeni randevu formunda "Kapora iste" kutusu.
- **Müşteri ekranları:** Onay ekranında ve Randevularım sayfasında kapora kutusu var: IBAN, açıklama kodu (ikisi için de kopyalama butonu), tutar ve kural metni. Son adımda iptal kuralı ayrıca gösteriliyor.
- **Grup randevusu:** Kapora kişi başı hesaplanıp toplanıyor ve randevuyu alana tek mesajla gidiyor. "Kapora ödendi" butonu grubun hepsini kesinleştiriyor.
- **Hatırlatma:** Kapora bekleyen ve "Bekliyor" durumundaki randevulara "yarın randevunuz var" hatırlatması gitmiyor. Kapora ödenince hatırlatma yeniden kuruluyor.
- **Kaporadan vazgeçme:** Yönetici, kapora bekleyen bir randevuyu doğrudan onaylarsa ya da tamamlarsa kapora şartı kalkıyor.
- **Geri al:** İade bekliyor ya da yandı durumundaki kapora yeniden Ödendi oluyor. İade edilmiş kapora olduğu gibi kalıyor ve uyarı gösteriliyor.
- **Yeni uç noktalar:**
  - `GET/PUT /api/admin/settings/deposit`
  - `GET /api/admin/deposits`
  - `POST /api/admin/appointments/{id}/deposit/paid`, `/refunded` ve `/resend`
  - `GET /api/deposit/info` (herkese açık, IBAN göstermez)
- **KVKK:** Amaçlar tablosuna kapora ödeme açıklaması, tutar ve durum satırı eklendi.

---

## 🔴 Hata düzeltmeleri

### 18.

- **Seçili saat butonu:** Bitiş saati ve "Senin için tutuluyor" etiketi eski koyu zemine göre renklendirilmişti, yeni açık zeminde okunmuyordu.
- **Tekrar hatırlatması:**
  - Randevudaki yalnızca ilk hizmete bakılıyordu.
  - Bir müşteriye birden fazla davet birikebiliyordu.
  - Müşteri yeniden randevu almış olsa da davet gidiyordu.
- **Grup randevusu indirimi:** Ayrı bir kodla hesaplanıyordu, artık aynı kuralı kullanıyor.
- **Son kontrol ekranındaki indirim:** Saat listesindeki eski veriye dayanıyordu. Artık saat tutma yanıtındaki `discountRate` ve `discountedPrice` kullanılıyor.
- **Örnek veri indirimi:** Örnek veri üretici kendi indirim kuralını kullanıyordu (hafta sonu dahil, %15). Artık ortak kuralı kullanıyor.
- **Taşınan randevunun hatırlatması:** Sürükleyerek taşınan randevunun 24 saat önceki hatırlatması eski saatte kalıyordu.
- **Çakışan randevular:** Araya sıkıştırılan bir randevu varken öndeki randevu iptal edildiğinde, Gelmedi olarak işaretlendiğinde, taşındığında ya da düzenlendiğinde ortak saat boş görünüyordu. Bu, çift rezervasyona yol açabiliyordu. Artık serbest kalan saatler, hâlâ aktif olan randevuya geri yazılıyor (`release_cells` / `reclaim_cells`).
- **Gelmedi randevular:** Gelmedi olarak işaretlenmiş randevular sürüklenip taşınabiliyordu. Artık taşınamıyor.
- **Sadakat seviyesi:** Ekranda ham seviye kodu (`BRONZ`) görünüyordu.

---

## Doğrulama

- `pytest`: **419 test geçti**. Yeni test dosyaları:
  - `test_kvkk_booking_consent.py`
  - `test_busy_slots.py`
  - `test_booking_cancellation.py`
  - `test_staff_remember_me.py`
  - `test_portfolio_admin.py`
  - `test_post_visit_rebooking.py`
  - `test_discount.py`
  - `test_push.py`
  - `test_manual_booking.py`
  - `test_deposit.py`
- `npx tsc --noEmit`: hatasız. `npm run build` önceki adımlarda başarılı oldu.
- Çalışan sunucuda kontrol: Çarşamba 09:00–11:00 saatleri %10 indirimli, 12:00 ve sonrası indirimsiz, Cumartesi hiç indirim yok. Push anahtarı uç noktası girişsiz 401, girişle 200 döndü. Elle randevu için müşteri arama, hizmet seçenekleri ve önizleme uç noktaları 200 döndü. Kapora ayarları, kapora listeleri ve `/api/deposit/info` 200 döndü (kapora kapalı).
- Tarayıcıda tıklanarak denenmedi:
  - Push bildiriminin cihaza gerçekten gelmesi
  - Admin kutu menüsünün telefondaki görünümü
  - Takvimdeki randevu ekleme/düzenleme formu
  - Sadakat rozeti
  - Kapora akışının uçtan uca denenmesi (açık hâlde)

## Bilinmesi gerekenler

- **Prod'a geçiş:**
  1. `alembic upgrade head` çalıştırılmalı. 0008–0013 arası migration'lar uygulanacak.
  2. Backend imajı yeniden build edilmeli (`pywebpush`).
  3. `python -m app.tools.vapid` çıktısı `deploy/.env`'e eklenmeli.
- **Geliştirme ortamı:**
  - `uvicorn --reload` bu makinede değişiklikleri algılamıyor. Backend kodu değişince sunucu elle yeniden başlatılmalı.
  - `next dev` açıkken `npm run build` çalıştırılmamalı, ikisi aynı `.next` klasörünü kullanıyor.
- **iPhone push:** iOS 16.4+, HTTPS ve "Ana Ekrana Ekle" ile yüklenmiş uygulama gerekiyor. `localhost` ile denenemez.
- **Ziyaret sonrası mesaj:** Gerçek Google ve Instagram linkleri girilmeden açılmamalı.
- **Tekrar daveti:** Kendi kuralı olmayan bir hizmete kategori kuralı, genel kural ya da önerilen tekrar süresi uygulanıyor. Bir hizmete hiç davet gitmemesi için o hizmete kural ekleyip kapatmak gerekiyor.
- **Eski örnek veri:** Yerel veritabanındaki eski demo randevular eski indirimleriyle duruyor. `python -m app.seed` tüm veriyi silip yeniden oluşturur.
- **Kapora:** Varsayılan olarak kapalı. Açmadan önce Admin → WhatsApp → Kapora kartına IBAN ve alıcı adı girilmeli. Kapora kontrolü 60 saniyede bir çalışıyor (`DEPOSIT_WATCH_SECONDS`, `0` = kapalı).
- **Telefonsuz müşteri:** Müşteri tablosunda telefon zorunlu olduğu için telefonsuz (walk-in) müşteri eklenemiyor.
- **Geri al'ın bilinen sınırları:**
  - Geri alınan randevunun iptal edilmiş WhatsApp onay mesajı yeniden kuyruğa alınmıyor.
  - Geri alma, tamamlanma sırasında iptal edilen eski tekrar davetini geri getirmiyor.
- **Puanlar harcanamıyor:** Sadakat puanlarını indirime ya da hediyeye çevirme özelliği yok.
- **Test veritabanları:** Yerel Docker'da agentların açtığı ayrı test veritabanları duruyor: `aurora_*_test`. Zararsızlar.
