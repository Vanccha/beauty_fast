# Aurora API — Akıllı Salon Randevu Sistemi (FastAPI backend)

Bu klasör, [`Vanccha/beauty_center_system`](https://github.com/Vanccha/beauty_center_system)
deposundaki Next.js + Prisma sisteminin **backend'inin FastAPI +
SQLAlchemy sürümüdür**. Orijinal repo yalnızca okundu; ona hiçbir yazma
işlemi (push/commit/PR) yapılmadı.

API sözleşmesi birebir korundu — yol adları, gövde alanları, `{ok, data}`
zarfı ve hata kodları aynı. Bu depodaki arayüz (`../frontend/`), `fetch`
adresini bu sunucuya çevirdiğinde (bkz. `frontend/next.config.mjs`
içindeki proxy) **değişiklik yapmadan** çalışır.

Ayırt edici taraf arayüz değil, altındaki **zamanlama motoru**:

- Bir paketin (çoklu hizmet) takvimde kapladığı **kesintisiz bloğu** hesaplar
  ve 110 dakikalık bir paketi asla 60 dakikalık bir boşluğa önermez.
- Hizmet süresini `aktif / pasif / aktif` olarak modeller. Saç boyasının
  ortasındaki 40 dakikalık **bekleme süresinde ustayı boşa düşürmez**; o
  pencereyi başka bir müşteriye açar (**shadow blocking**).
- Aynı slota eşzamanlı iki istek geldiğinde çakışmayı **veritabanı
  seviyesinde** reddeder (Redis yok, uygulama içi kilit yok).

> **Randevu akışındaki iki hata bu sürümde düzeltildi.** Orijinal repodaki
> kusurların ne olduğu, nasıl göründüğü ve nasıl giderildiği
> [§ Düzeltilen hatalar](#düzeltilen-hatalar) bölümünde dosya/satır
> referanslarıyla anlatılıyor.

---

## Kurulum

Gerekenler: Python 3.11+ ve Docker (PostgreSQL için). Veritabanı
PostgreSQL'dir; başka bir veritabanı adresiyle uygulama açılmaz. Komutlar
bu klasörün (`backend/`) içinden çalıştırılır. Şema Alembic
migration'larıyla yönetilir; geliştirme modunda sunucu ve seed açılışta
`alembic upgrade head` işini kendiliğinden yapar.

```bash
cd backend
docker compose up -d db         # PostgreSQL :5432 (+ testler için aurora_test)
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

copy .env.example .env          # Linux/macOS: cp .env.example .env
python -m app.seed              # demo verisi (deterministik)
uvicorn app.main:app --reload   # http://localhost:8000
```

Etkileşimli API dokümanı: <http://localhost:8000/docs> (yalnızca geliştirme modunda)

`DATABASE_URL` verilmezse lokal adres
(`postgresql+psycopg://aurora:aurora@localhost:5432/aurora`) kullanılır;
üretimde bu adresle uygulama açılmaz, `DATABASE_URL` zorunludur.

Arayüz (Next.js) için ayrı bir kurulum ve komut seti gerekir — bkz.
[`../frontend/README.md`](../frontend/README.md). Seed, personel ve
portfolyo fotoğrafları için `frontend/public/photos/` klasörünü okur; en
gerçekçi demo için önce `frontend`'de `npm run photos` çalıştırıp sonra
`python -m app.seed` komutunu çalıştırın (sıra önemlidir, ayrıntı için
[kök README'deki Hızlı başlangıç](../README.md#hızlı-başlangıç)).

### Demo giriş bilgileri

| Rol | Telefon | Şifre |
|---|---|---|
| Salon sahibi | `05551110001` | `admin123` |
| Yönetici | `05551110002` | `merve123` |
| Personel | `05551110003` | `zeynep123` |
| Personel | `05551110004` | `selin123` |

**Müşteri girişi şifresizdir:** `POST /api/auth/otp/send` ile herhangi bir
demo numarasına (`05321010000` … `05321010024`) kod isteyin. SMS gönderilmez
— kod sunucu konsoluna yazılır ve `APP_ENV != production` iken yanıtın
`devCode` alanında döner. `.env` içindeki `DEV_OTP_CODE=123456` ayarlıyken
kod sabittir.

> Üretim modunda (`APP_ENV=production`) `devCode` **hiçbir koşulda**
> dönmez, yalnızca konsola yazılır. Bu kasıtlıdır.

### Komutlar

| Komut | Ne yapar |
|---|---|
| `uvicorn app.main:app --reload` | Geliştirme sunucusu |
| `python -m app.seed` | Demo verisini yeniden üretir (deterministik) |
| `pytest` | 190 testin tamamı (Docker'daki `aurora_test` veritabanında) |
| `alembic upgrade head` | Şemayı en güncel migration'a getirir (üretimde dağıtım adımı) |
| `alembic revision --autogenerate -m "..."` | Model değişikliğinden yeni migration üretir |
| `pytest tests/test_concurrency.py` | Yalnızca yarış koşulu testleri |
| `pytest tests/test_booking_bugfix.py` | Düzeltilen hataların regresyon testleri |

---

## Teknoloji seçimleri ve gerekçeleri

| Katman | Seçim | Neden |
|---|---|---|
| Framework | FastAPI | Tip ipuçlarından doğrulama + otomatik OpenAPI; ince uç noktalar |
| Doğrulama | Pydantic v2 | Zod'un karşılığı: şema tek yerde, hata mesajı tek biçimde |
| ORM | SQLAlchemy 2.0 | Prisma'nın karşılığı; `Mapped[...]` ile tipli modeller |
| Veritabanı | PostgreSQL | Geliştirme, test ve üretim aynı veritabanında; satır kilitleri (`FOR UPDATE`, `SKIP LOCKED`) ve hata kodları buna göre yazıldı |
| Şema | Alembic | `migrations/` altında; `create_all` kullanılmaz |
| Şifre | `hashlib.scrypt` | `bcrypt`/`passlib` ek bağımlılık ister; scrypt standart kütüphanede ve aynı sınıfta bir KDF |
| Oturum | Opak token + DB kaydı | JWT'de iptal için yine tablo gerekirdi; token hiçbir bilgi taşımaz |
| Kilitleme | **Redis yok** — DB unique constraint + TTL | Aşağıya bakınız |

### Neden Redis değil?

Slot çakışması için yaygın çözüm Redis üzerinde dağıtık kilittir. Burada
bilerek kullanılmadı:

Zaman **5 dakikalık hücrelere** bölünür (`cell_index = dakika // 5`). Bir
randevu ya da geçici rezervasyon, kapladığı her hücre için `occupancy_cell`
tablosuna bir satır yazar. Tablodaki

```sql
UNIQUE (owner_type, owner_id, date, cell_index)
```

kısıtı sayesinde **aynı ustanın aynı 5 dakikasına ikinci bir kayıt yazmak
veritabanı tarafından reddedilir**. Garanti uygulama katmanında değil,
motorda olduğu için "önce kontrol et, sonra yaz" (TOCTOU) açığı yoktur.
`pytest tests/test_concurrency.py` bunu 5 eşzamanlı istekle doğrular.

PostgreSQL'de yazmalar sıraya girmez (READ COMMITTED). Bu yüzden
oku-değiştir-yaz yapan yerler ayrıca korunur: stok ve sadakat puanı
satırları `SELECT ... FOR UPDATE` ile kilitlenir, durum değişikliği
`status NOT IN (terminal)` koşullu UPDATE ile yapılır, OTP deneme hakkı
atomik UPDATE ile ayrılır.

---

## Mimari — üç katman

```
app/core/      SAF algoritmalar. ORM bilmez, girdileri dışarıdan alır, testlidir.
app/services/  Köprü. Veritabanını okur, saf katmana besler, sonucu şekillendirir.
app/api/       FastAPI router'ları. İş mantığı İÇERMEZ.
```

Bu ayrım kasıtlıdır: zamanlama motorunu test etmek için veritabanı gerekmez
ve uçlar ince kalır. Yeni bir uç eklerken iş mantığını `app/services/`
içine koy, router'ı sarmalayıcı bırak.

```
app/
├── main.py            uygulama + CORS + hata işleyicileri
├── config.py          ortam değişkenlerinin tek okuma noktası
├── db.py              engine, oturum, init_db (alembic upgrade head)
├── models.py          36 tablo, tamamı yorumlu
├── deps.py            yetki kapıları (require_staff / require_customer / …)
├── http.py            {ok, data} zarfı + hata kodu sözleşmesi
├── errors.py          AppError / SlotConflictError / VersionConflictError
├── intervals.py       aralık cebiri (saf)
├── time_utils.py      gün-yerel dakika temsili
├── uploads.py         magic-number doğrulamalı lokal yükleme
├── seed.py            deterministik demo verisi (python -m app.seed)
├── auth/              scrypt şifre, cookie oturum, OTP
├── core/              SAF algoritmalar
│   ├── package_layout.py   paket yerleşimi + sıkıştırma
│   ├── availability.py     bitişik blok bulma (3 boyutlu)
│   ├── occupancy.py        doluluk hücresi üretimi
│   ├── opportunity.py      fırsat saatleri (Bayes shrinkage)
│   ├── loyalty.py          sadakat puanı + seviye + erime
│   ├── risk_score.py       gölge risk skoru (KVKK uyumlu)
│   ├── segmentation.py     CRM segmentleri
│   ├── color_affinity.py   renk eğilimi
│   ├── campaigns.py        kampanya hedefleme kural motoru
│   ├── reminder_rules.py   hatırlatma kural motoru (4 formül)
│   └── recommendation.py   hizmet önerisi + gölge upsell
├── services/          algoritma ↔ veritabanı köprüsü
└── api/               auth · catalog · slots · appointments · public · admin
```

---

## Algoritmalar

Tüm algoritmalar `app/core/` altında **saf fonksiyonlar** olarak yazılmıştır:
veritabanı bilmezler, girdilerinin tamamı dışarıdan gelir ve her biri birim
testlidir.

### 1. Hizmet süre modeli — shadow blocking'in temeli

```
|<-- active_before -->|<-- passive -->|<-- active_after -->|<-buffer->|
^ usta MEŞGUL          ^ usta SERBEST  ^ usta MEŞGUL         ^ MEŞGUL
```

Saç boyası: `30 + 40 + 20 = 90 dk`. Ortadaki **40 dakikada usta serbesttir**.

- `shadow_host_allowed` — bu hizmetin pasif penceresi misafire açılabilir mi?
- `shadow_guest_allowed` — bu hizmet başka bir randevunun penceresine girebilir mi?

Doluluk hücreleri yazılırken **pasif süre için STAFF hücresi yazılmaz**
(usta serbest kalır), ama CUSTOMER hücreleri yazılır (müşteri salondadır).
Shadow blocking bu yüzden ekstra bir "özellik" değil, veri modelinin doğal
sonucudur (`app/core/occupancy.py`).

### 2. Paket yerleşimi ve sıkıştırma — `core/package_layout.py`

```
Saç boyası (30 + 40 bekleme + 20 + 10 buffer) + Kaş alma (15)
  Sıralı  : 115 dk
  Sıkışık : 100 dk   ← kaş alma, boyanın beklemesinde yapılır
```

Müşteri 15 dakika erken çıkar; kalan 25 dakikalık pencere hâlâ **dış** bir
müşteriye açıktır.

### 3. Bitişik blok bulma — `core/availability.py`

Üç boyut aynı anda değerlendirilir: hizmet süresi, usta müsaitliği ve
kaynak/cihaz kapasitesi.

Kritik kural: blok, çalışma penceresi içinde **tek parça** olmalıdır
(`contained_in_any`). İki ayrı boşluğa bölünerek sığması kabul edilmez — bu
yüzden 110 dakikalık paket 60 dakikalık boşluğa **önerilmez** ve kullanıcı
boş bir ekranla değil, nedenini söyleyen bir mesajla karşılaşır.

Kapasitesi 1'den büyük kaynaklar (3 boya koltuğu gibi) hücre yazmaz; sorgu
zamanında **sweep-line** ile doygunluk aralıkları hesaplanır
(`intervals.saturated_intervals`).

### 4. Eşzamanlılık kalkanı — `services/soft_lock.py`, `services/appointment.py`

```
acquire_slot_lock()  →  transaction {
    1. süresi geçmiş LOCK hücrelerini sil
    2. aynı oturumun eski kilitlerini bırak
    3. SlotLock kaydı oluştur
    4. OccupancyCell satırlarını yaz   ← çakışma BURADA, IntegrityError ile
}
```

TTL 5 dakikadır. Randevuya çevirirken `confirm_appointment_from_lock`,
kilidin `start_min/end_min` değerini yeniden hesaplanan paketle
karşılaştırır — istemci, kilitlediğinden farklı bir bloğu kaydettiremez.

Taşıma (sürükle-bırak) **optimistic locking** kullanır:

```python
updated = db.execute(
    update(Appointment)
    .where(Appointment.id == appointment_id, Appointment.version == expected_version)
    .values(..., version=Appointment.version + 1)
).rowcount
if not updated:
    raise VersionConflictError()
```

### 5. Gölge risk skoru — `core/risk_score.py`

Salonlar arası no-show geçmişinden 0–100 arası skor üretir.

- **KVKK:** telefon numarası açık tutulmaz; havuz anahtarı
  `HMAC-SHA256(normalize(phone), PHONE_HASH_SECRET)`. Dönen nesne yalnızca
  `{score, label, totalAppointments, noShowRate, windowMonths, message}`
  içerir — başka salonun adı, randevu detayı **asla** dönmez.
- Zaman ağırlıklı: `w(t) = 0.5 ** (yaşGün / 60)`. Yakın tarihli gelmemeler
  eskilerden ağır basar.
- Az veride Laplace düzeltmesi: `(Σw_noshow + α) / (Σw_all + α + β)`,
  `α = 1`, `β = 2`.
- Etiket: `<20 DÜŞÜK`, `20–45 ORTA`, `>45 YÜKSEK`, 3 olaydan az ise
  `YETERSIZ_VERI` (tek olayla müşteri damgalanmaz).

### 6. Sadakat motoru — `core/loyalty.py`

```
puan = 0.1 × tutar
     × frequency_multiplier(son ziyaretten bu yana gün)
     × opportunity_multiplier(fırsat saati indirimi)
     × tier_multiplier(seviye)
```

Seviye eşikleri BRONZ 0 / GÜMÜŞ 500 / ALTIN 1500 / VIP 4000. Atıl puan
`0.5 ** (atılGün / 180)` ile erir; ilk 90 gün **grace period**'dur.

### 7. Fırsat saatleri — `core/opportunity.py`

Ham doluluk oranı doğrudan kullanılmaz: küçük örneklemde "salı 10:00 %0
dolu" yanıltıcıdır. **Bayes shrinkage** uygulanır —

```
düzeltilmiş = (ham × n + şubeOrtalaması × priorStrength) / (n + priorStrength)
```

— ve indirim yalnızca düzeltilmiş doluluk eşiğin altına düştüğünde, `%5`'lik
adımlara yuvarlanarak açılır. Bu saatlerde alınan randevular sadakat puanı
çarpanı da alır: ölü saati doldurmak teşvik edilir.

> **Kalibrasyon notu.** Varsayılan `threshold = 0.55`, yoğun bir salon
> varsayar. Demo verisinde 4 personel / 180 gün / 450 randevu ile tepe
> doluluk ~%25'te kalır; bu yüzden ısı haritasında her saat bir miktar
> indirim alır (sabahlar %20, akşamlar %10 — yani sıralama doğru, ölçek
> cömert). Gerçek veride eşiği salonun kendi doluluk seviyesine çekmek için
> `OpportunityConfig.threshold` tek değişim noktasıdır.

### 8. Hatırlatma kural motoru — `core/reminder_rules.py`

Aralıklar koda gömülü **değildir**; `reminder_rule` tablosundaki formül +
parametreden hesaplanır:

| Formül | Kullanım | Parametre |
|---|---|---|
| `FIXED` | sabit aralık | — |
| `GROWTH` | dip boya | `{mmPerMonth, toleranceMm}` |
| `PRODUCT_LIFETIME` | kalıcı oje / jel ömrü | `{productDays: {...}}` |
| `SEASONAL` | mevsimsel cilt bakımı | `{monthFactors: {...}}` |

Kural seçim önceliği: hizmet eşleşmesi > kategori > şube geneli; eşitlikte
`priority`.

### 9. Diğerleri

- **Segmentasyon** (`core/segmentation.py`) — VIP / SADIK / RİSKLİ / UYUYAN / YENİ.
- **Renk eğilimi** (`core/color_affinity.py`) — albüm etiketlerinin zaman
  ağırlıklı frekansı, renk ailesine eşlenir.
- **Kampanya hedefleme** (`core/campaigns.py`) — kupon kodu yok; JSON kural
  motoru müşteri profilini değerlendirir.
- **Hizmet önerisi** (`core/recommendation.py`) — uyum, popülerlik,
  güvenilirlik, dakika başına gelir artı; kaynak çekişmesi ve takvim
  parçalanması eksi puan.
- **Stok** (`services/stock.py`) — `UNIQUE(appointment_id, item_id)` ile
  idempotent düşüm; aynı randevu iki kez tamamlansa bile stok bir kez düşer.

---

## Düzeltilen hatalar

Randevu akışı, orijinal repo üzerinde uçtan uca incelendi. "Hizmeti/saati
iki kez seçmek zorunda kalmak" şikâyetini üretebilecek **iki ayrı kusur**
bulundu; üçüncü olarak da ekranda yazan süreyle kaydedilen sürenin
ayrışabildiği bir tutarsızlık tespit edildi. Üçü de bu sürümde düzeltildi ve
regresyon testleriyle kilitlendi (`tests/test_booking_bugfix.py`).

### Hata 1 — kendi geçici rezervasyonun, kendi saatini gizliyor

**Nerede (orijinal Next.js reposu):** `src/lib/server/availability.ts:230-268`

Müsaitlik sorgusu, o anki ziyaretçiyi hiç tanımıyor: süresi dolmamış **tüm**
`LOCK` hücreleri "meşgul" sayılıyor, kilidi tutan oturumun kendisi dahil.

```ts
prisma.occupancyCell.findMany({
  where: { ownerType: 'STAFF', ownerId: staff.id, date: request.date,
           kind: 'LOCK', expiresAt: { gt: now } },   // ← oturum filtresi YOK
})
```

**Nasıl görünüyor:** Kullanıcı 3. adımda saati seçip "Bu saati tut"a basıyor
(slot 5 dakikalığına kilitleniyor), 4. adımda "Geri"ye dönüyor. Arayüzdeki
geri düğmesi kilidi serbest bırakmıyor (orijinal repoda
`src/app/(shop)/randevu/booking-flow.tsx:760` — `setStep(s => s - 1)`,
`releaseLock()` çağrısı yok) ve adım 3'e dönüldüğünde müsaitlik yeniden
yükleniyor. Sonuç: **kullanıcının az önce seçtiği saat listede yok.** Saat
görünmediği için kullanıcı başka bir saat ya da baştan hizmet seçimi yapmak
zorunda kalıyor; kilit TTL'i (5 dk) dolana kadar da o saat kendisine
kapalı.

**Düzeltme** (`app/services/availability.py`): müsaitlik sorgusu
`viewer_key` (ziyaretçi çerezi) alır ve o oturuma ait kilitleri meşgul
kümesinden çıkarır. Başkalarının kilitleri eskisi gibi engelleyicidir.

```python
if own_lock_ids:
    lock_cell_query = lock_cell_query.where(OccupancyCell.lock_id.notin_(own_lock_ids))
```

Ayrıca yanıt iki yeni alan taşır:

- `slots[].heldByYou` — bu saat şu anda senin için tutuluyor,
- `yourLock` — açık kilidin özeti (id, saat, `expiresAt`).

Arayüzün geri dönerken kilidi bırakması için de yeni bir uç eklendi:
`GET /api/slots/lock/active`.

**Arayüz tarafı (`../frontend/src/app/(shop)/randevu/booking-flow.tsx`).**
Hata 1'in asıl kullanıcı şikâyeti — "giriş yaptım, hizmetleri yeniden
seçmem gerekti" — arayüz katmanında kapatıldı:

- Misafir 5. adımda (`Randevuyu onayla`) `MEMBERSHIP_REQUIRED` alırsa, o ana
  kadarki tüm seçim (hizmetler, usta, saat, kilit, notlar, tasarım linki)
  `sessionStorage`'a (`randevu-taslak-v1`) yazılır ve kullanıcı
  `/giris?next=/randevu?resume=1&services=...` adresine yönlendirilir.
  Girişten dönünce (`?resume=1`) taslak geri okunur; kilit hâlâ geçerliyse
  (aynı `viewer_key` çerezi, `GET /api/slots/lock/active` ile doğrulanır)
  kullanıcı doğrudan 5. adıma döner — hizmet/usta/saat seçimini tekrarlamaz.
- "Geri" ile saat seçiminden (3. adım) öncesine dönmek artık kilidi
  sunucuda da bırakır (`releaseLock`/`goToStep` → `DELETE
  /api/slots/lock/{id}`); eskiden yalnızca `setStep` çağrılıyor, kilit arka
  planda sayaç bitene kadar yaşıyordu.
- Saat ızgarasında `heldByYou` alanı bir rozetle ("Bu saat şu anda senin
  için tutuluyor") gösterilir.
- Personel seçilmemişse paket özetinin **nominal** (`package.isNominal`)
  olduğu, ekranda "yaklaşık" ibaresiyle ve bir dipnotla açıkça belirtilir.

### Hata 2 — aynı hizmeti iki kez seçmek imkânsız

**Nerede (orijinal Next.js reposu):** `src/lib/server/catalog.ts:118`,
`src/app/api/slots/lock/route.ts:46`, `src/app/api/appointments/route.ts:62`

Personel yetkinliği **sayı karşılaştırmasıyla** doğrulanıyor:

```ts
return staff.filter((s) => s.services.length === serviceIds.length);   // catalog.ts:118
if (link.length !== body.serviceIds.length) throw new AppError(...);   // lock route:46
```

`serviceIds` içinde tekrar eden bir id varsa (örn. `[6, 6]` — iki kişi için
kaş alma, ya da paketin ikinci bir seansı) yetkinlik satırı sayısı istenen
kalem sayısından az kalır:

- `/api/availability` → *"Seçtiğiniz hizmetlerin tamamını yapabilen personel
  bulunamadı"* (hiç slot çıkmaz),
- `/api/slots/lock` ve `/api/appointments` → *"Seçilen personel bu
  hizmetlerin tamamını yapmıyor"* (400).

Bu bir tasarım kararı da değil: aynı sistemin stok katmanı tekrarı **açıkça
destekliyor** (orijinal repoda `src/lib/services/inventory/stock.ts:75` —
*"Bir hizmet randevuda birden fazla kez geçiyorsa o kadar kez sayılır"*).
Yani veri modeli tekrarı kaldırıyor, yalnızca yetkinlik kontrolü kaldırmıyor.

**Düzeltme** (`app/services/catalog.py`): karşılaştırma **küme
kapsamasına** çevrildi — personelin yetkinlik kümesi, istenen benzersiz
hizmet kümesini kapsıyorsa yeterlidir. Tekrar eden kalemler paket
yerleşiminde ayrı ayrı yer alır, fiyat ve süre iki kat hesaplanır, stok iki
kez düşer.

```python
return [s for s in staff_rows if needed.issubset({link.service_id for link in s.services})]
```

Yetkinlik kontrolü gevşetilmedi: yapamadığı bir hizmet istenen personel
hâlâ reddedilir (`test_staff_without_skill_is_still_rejected`). Paket
boyutu ayrıca `MAX_PACKAGE_ITEMS = 10` ile sınırlandı.

### Hata 3 — paket özeti yanlış ustaya göre hesaplanıyor

**Nerede (orijinal Next.js reposu):** `src/lib/server/availability.ts:223-228, 341`

Yanıttaki `package` özeti (toplam süre, fiyat, sıkıştırma kazancı) **ilk
uygun personelin** hız çarpanıyla hesaplanıp tüm listeye basılıyor:

```ts
if (!referenceLayout) referenceLayout = layout;   // ilk personel kazanır
...
const layout = referenceLayout ?? layoutPackage(specs);
```

Müşteri daha yavaş bir usta seçtiğinde (seed verisinde Selin'in
`speedFactor = 1.1`) ekranda "110 dk" yazarken kilitlenen blok 125 dakika
olur. Kullanıcı yanlış bilgiyle karar verir.

**Düzeltme:**

- `staffId` verilmişse özet **doğrudan o personele** göre hesaplanır,
- verilmemişse **nominal** (`speed_factor = 1.0`) özet döner ve bu durum
  `package.isNominal` / `package.basedOnStaffId` alanlarıyla açıkça
  bildirilir. Her personel zaten kendi `totalMin` / `savedMin` değerini
  taşıyor.

### Neden bu üçü "iki kez seçmek" gibi görünüyor?

| | Kullanıcının gördüğü |
|---|---|
| Hata 1 | "Saati seçtim, geri döndüm, saat kayboldu — baştan seçmem gerekti." |
| Hata 2 | "Aynı hizmetten iki tane seçtim, sistem uygun personel/saat bulamadı." |
| Hata 3 | "Süre 110 dk yazıyordu, onayda 125 dk çıktı." |

İlk ikisi doğrudan "seçimi yeniden yapmak" sonucunu doğuruyor. Üçüncüsü
sessiz: kullanıcı fark etmezse takvim yanlış bilgiyle doluyor.

### Hata 1'in arayüzle birlikte gün yüzüne çıkardığı ek açıklar

Misafir → giriş → onay akışı uçtan uca test edilirken ortaya çıkan dört
küçük ama gerçek açık, aynı serüvende kapatıldı (regresyon testleri:
`tests/test_booking_login_resume.py`):

- **Kilit yalnızca üretilmiş bir slota alınabilir**
  (`app/api/slots.py` — `POST /api/slots/lock`). Eskiden kilit ucu yalnızca
  hücre çakışmasına bakıyordu; mesai dışı bir saat (ör. 03:00), geçmiş bir
  gün ya da bugünün geçmiş bir saati için de kilit — ve ardından randevu —
  alınabiliyordu. `startMin` artık motorun o usta için ürettiği slotlardan
  biri değilse `SLOT_UNAVAILABLE` döner.
- **Kilit sahipliği üye bazında da korunur**
  (`assert_lock_valid`, `app/services/soft_lock.py:270`). Sahiplik iki
  katmanlıdır: kilit her zaman aynı tarayıcıya (`visitor_key`) ait olmalı;
  kilit bir üye oturumuyla alındıysa onaylayan da **aynı** üye olmalıdır —
  aksi halde `FORBIDDEN`. Misafirken alınan kilit (`customer_id` boş),
  giriş yapıldıktan sonra aynı tarayıcıdan onaylanabilir; bu, "giriş yap,
  sonra onayla" akışının şartıdır.
- **`CUSTOMER_OVERLAP`** (`app/services/soft_lock.py` — `conflict_error`).
  Hücre çakışması yalnızca müşterinin **kendi takvimindeyse** (aynı saatte
  zaten başka bir randevusu varsa) bu artık genel `SLOT_TAKEN` yerine ayrı
  bir kodla bildirilir; aksi halde kullanıcı saat değiştirmeden de aynı
  "başka biri aldı" hatasını görmeye devam ederdi.
- **`shadowParentId` istemciden körlemesine kaydedilmez**
  (`app/api/appointments.py` — `POST /api/appointments`). Sunucu, bağı
  yalnızca aynı usta + aynı gün + `PENDING`/`CONFIRMED` bir randevunun
  bloğu içinde başlayan bir slot için kurar; uymuyorsa `shadowParentId`
  sessizce `None`'a düşürülür — panelde yanlış bir "gölge" ilişkisi
  gösterilmez.
- **Açık yönlendirme (open redirect) düzeltmesi**
  (`../frontend/src/app/(shop)/giris/page.tsx` — `safeNext`). `?next=`
  parametresi yalnızca site içi bir yol kabul eder (`/` ile başlamalı,
  `//` veya `/\` ile başlayamaz); aksi halde `/hesabim`'e düşer. Böylece
  `/giris?next=https://kötü.site` gibi bir bağlantı girişten sonra
  kullanıcıyı dış bir siteye yönlendiremez.

### Bu düzeltmeleri doğrulayan testler

```bash
pytest tests/test_booking_bugfix.py -v
```

| Test | Ne kanıtlıyor |
|---|---|
| `test_own_lock_does_not_hide_own_slot` | Kendi kilidin kendi saatini gizlemiyor |
| `test_other_visitors_lock_still_blocks` | Başkasının kilidi hâlâ engelliyor |
| `test_anonymous_request_sees_all_locks_as_busy` | `viewer_key` yoksa güvenli taraf |
| `test_duplicate_services_keep_capable_staff` | `[6, 6]` personeli elemiyor |
| `test_duplicate_services_produce_two_items` | İki kalem, iki kat süre/fiyat |
| `test_availability_supports_duplicate_services` | Tekrarlı paketle slot üretiliyor |
| `test_staff_without_skill_is_still_rejected` | Yetkinlik kontrolü gevşemedi |
| `test_package_summary_follows_selected_staff` | Ekrandaki süre = kilitlenen süre |
| `test_duplicate_service_consumes_stock_twice` | Malzeme iki kez düşüyor |
| `test_booking_the_same_service_twice` (API) | Uçtan uca: 2× Kaş Alma = 300 TL |

Giriş sonrası devam (login-resume) senaryosu ayrı bir dosyada:

```bash
pytest tests/test_booking_login_resume.py -v
```

| Test | Ne kanıtlıyor |
|---|---|
| `test_lock_rejects_start_outside_generated_slots` | Mesai dışı bir saate kilit alınamaz (`SLOT_UNAVAILABLE`) |
| `test_lock_rejects_past_date` | Geçmiş bir tarihe kilit alınamaz |
| `test_guest_lock_survives_login_and_can_be_confirmed` | Misafirken alınan kilit, girişten sonra aynı tarayıcıdan onaylanabilir |
| `test_other_member_cannot_confirm_members_lock_on_same_browser` | Bir üyenin kilidini aynı tarayıcıda başka bir üye onaylayamaz (`FORBIDDEN`) |
| `test_customer_overlap_is_not_reported_as_slot_taken` | Müşterinin kendi çakışması genel `SLOT_TAKEN` yerine `CUSTOMER_OVERLAP` ile bildirilir |
| `test_customer_overlap_detected_when_guest_lock_is_confirmed` | Aynı kural, misafir kilidi girişten sonra onaylanırken de çalışır |
| `test_relocking_same_slot_is_not_blocked_by_own_old_lock` | Aynı saati yeniden kilitlemek kendi eski kilidine takılmaz |
| `test_bogus_shadow_parent_is_not_stored` | İstemcinin gönderdiği `shadowParentId` doğrulanmadan kaydedilmez |
| `test_other_visitors_lock_still_reports_held_until` | Başkasının kilidi hâlâ `heldUntil` bilgisiyle engelleyici |

---

## API

Tüm yanıtlar aynı zarfı kullanır:

```jsonc
// başarı
{ "ok": true, "data": { ... } }
// hata
{ "ok": false, "error": { "code": "SLOT_TAKEN", "message": "…", "details": { … } } }
```

`code` alanı istemci için makine-okunur sözleşmedir: `MEMBERSHIP_REQUIRED`
giriş modalını açar, `SLOT_TAKEN` slot ızgarasını tazeler,
`VERSION_MISMATCH` sürükle-bırak hareketini geri alır.

### Herkese açık

| Uç | Açıklama |
|---|---|
| `GET /api/health` | Ayakta mı |
| `GET /api/me` | Oturum sahibi + kişiselleştirilmiş karşılama |
| `GET /api/showcase` | Açılış sayfasının tüm verisi (istatistik, kategori, ekip, yorum, galeri) |
| `GET /api/catalog/services` | Kategoriler + hizmetler, **öneri sırasıyla** |
| `GET /api/catalog/staff?serviceIds=1,2` | Paketin tamamını yapabilen personel |
| `GET /api/portfolio?category=sac` | Galeri |
| `GET /api/reviews?minRating=&staffId=` | Yayınlanmış yorumlar |
| `POST /api/availability` | **Zamanlama motoru** — uygun saatler, paket özeti, upsell |
| `POST /api/slots/view` | "Bu saate kaç kişi baktı" (gerçek, tekil sayım) |
| `POST /api/cron/sweep` | Bakım: kilit/oturum temizliği + bildirim kuyruğu |

### Oturum

| Uç | Açıklama |
|---|---|
| `POST /api/auth/otp/send` | Müşteriye doğrulama kodu (numara sızdırılmaz) |
| `POST /api/auth/otp/verify` | Kodu doğrula, oturum aç, gerekiyorsa hesap aç |
| `POST /api/auth/staff/login` | Personel girişi (telefon + şifre) |
| `POST /api/auth/logout` | Gövde: `{"scope": "staff"}`, `"customer"` veya `"all"` (varsayılan) |

### Randevu (müşteri)

| Uç | Açıklama |
|---|---|
| `GET /api/me/album` | Müşterinin kendi işlem geçmişi albümü (gizli usta notları bu uçta hiç sorgulanmaz) |
| `POST /api/slots/lock` | Saati 5 dakikalığına tut (DB unique kısıtıyla korunur) |
| `GET /api/slots/lock/active` | Bu oturumun açık kilidi ★ *yeni* |
| `DELETE /api/slots/lock/{id}` | Kilidi hemen bırak |
| `POST /api/appointments` | Kilidi kalıcı randevuya çevir (üyelik gerekir) |
| `GET /api/appointments/mine` | Yaklaşan + geçmiş randevular |
| `GET /api/appointments/{id}` | Detay (müşteri yalnızca kendisininkini görür) |
| `PATCH /api/appointments/{id}` | Durum (müşteri yalnızca `CANCELLED`) |
| `POST /api/appointments/{id}/design` | Tasarım görseli veya bağlantısı |
| `POST /api/reviews` | Tamamlanmış randevuya yorum (dört kapı) |

### Personel paneli (`require_staff`)

| Uç | Açıklama |
|---|---|
| `GET /api/admin/dashboard` | Bugünün randevuları, kritik stok, ciro ★ *yeni* |
| `GET /api/admin/notifications` | Bildirim kuyruğu (en yakın 25) ★ *yeni* |
| `GET /api/admin/calendar?date=` | Gün görünümü; meşgul ve **pasif** dilimler ayrı |
| `PATCH /api/admin/appointments/{id}/move` | Sürükle-bırak taşıma (optimistic locking) |
| `PATCH /api/admin/appointments/{id}/status` | Durum + tüm yan etkiler tek transaction |
| `GET /api/admin/customers` | Liste + segment rozeti + salon içi risk |
| `GET /api/admin/customers/{id}` | CRM kartı: risk, renk eğilimi, **gizli notlar**, albüm |
| `POST/DELETE /api/admin/customers/{id}/allergy` | Alerji ikazı |
| `POST/DELETE /api/admin/customers/{id}/note` | Gizli usta notu |
| `POST/DELETE /api/admin/customers/{id}/photo` | İşlem geçmişi albümü |
| `GET/POST/PATCH /api/admin/inventory` | Stok + kritik uyarılar |
| `GET/POST/PATCH /api/admin/campaigns` | Kampanyalar (JSON kural motoru) |
| `GET/POST/PATCH /api/admin/reminder-rules` | Hatırlatma kuralları + örnek hesap |
| `GET /api/admin/reviews`, `PATCH /api/admin/reviews/{id}` | Moderasyon (metin/puan **değiştirilemez**) |
| `GET /api/admin/stats/opportunity` | Fırsat saati ısı haritası |
| `GET /api/admin/portfolio` | Galeri yönetim listesi ★ *yeni* |
| `POST/DELETE /api/admin/portfolio` | Galeri yönetimi |

`POST`/`PATCH` uçlarından bazıları `MANAGER` rolü ister (kampanya, kural,
yeni stok kalemi). Rol hiyerarşisi: `OWNER > MANAGER > STAFF`.

---

## Veri modeli

36 tablo, tamamı `app/models.py` içinde yorumlu. Öne çıkan üçü:

- **`occupancy_cell`** — yarış koşulu savunmasının veritabanı tarafındaki
  garantisi. `UNIQUE(owner_type, owner_id, date, cell_index)`.
- **`phone_risk_event`** — salonlar arası no-show havuzu. `phone_hash`
  tutar, ham numara **tutmaz**; `salon_id` yalnızca veri sahipliği (silme
  hakkı) içindir ve hiçbir API yanıtında dönmez.
- **`review`** — vitrindeki sosyal kanıtın kaynağı. `appointment_id`
  **unique**: bir randevu bir kez değerlendirilir. Yorum tamamlanmış bir
  randevuya bağlıysa `is_verified` işaretlenir — rozet bir iddia değil,
  kısıtın sonucudur.

`enum` yerine dokümante edilmiş `String`, JSON yerine JSON metni tutan
`String` alanlar kullanılmıştır (Prisma şemasıyla aynı tercih; yeni bir
durum değeri eklemek migration gerektirmez).

---

## Testler

```bash
pytest                        # 190 test
pytest tests/test_concurrency.py
```

| Dosya | Kapsam |
|---|---|
| `test_intervals` | aralık cebiri, sweep-line doygunluk |
| `test_package_layout` | 110 dk paket, sıkıştırma, gölge pencere, **tekrarlı hizmet** |
| `test_availability` | ★ 110 dk paket 60 dk boşluğa girmiyor, shadow fill, kaynak doygunluğu |
| `test_scoring` | risk, sadakat, fırsat, segment, renk, kampanya |
| `test_reminder_rules` | dört formül + kural önceliği |
| `test_recommendation` | öneri sıralaması, gölge upsell |
| `test_concurrency` | ★ 2 ve 5 eşzamanlı istekten **tam 1** başarı; optimistic locking; stok idempotensi |
| `test_booking_bugfix` | ★ düzeltilen üç hatanın regresyonu |
| `test_status_version` | durum değişikliğinin döndürdüğü `version` = veritabanındaki değer |
| `test_api` | uçtan uca API: zarf, yetki kapıları, randevu akışı, yorum kapıları |
| `test_admin_views` | ★ panel sayfalarının beslendiği uçlar: bildirim kuyruğu, galeri listesi, fırsat saati bayrakları, kampanya hedef kitlesi, hatırlatma örnek önizlemesi |
| `test_whatsapp_welcome` | ★ İlk mesajda karşılama: tek sefer garantisi, tanıdık kişi kuralları (OTP/hatırlatma/personel/geçmiş), `@lid`, gruplar, eski mesajlar, panel ayarları |
| `test_messaging` | ★ Evolution istemcisi (sahte sunucu), OTP'nin WhatsApp'tan gönderimi, bağlantı kopukken hızlı hata, kuyrukta yeniden deneme/geri çekilme, yarım kalan gönderimin kurtarılması |
| `test_security` | ★ OTP kaba kuvvet koruması, deneme sınırları, bakım ucu yetkisi, üretim yapılandırma doğrulaması, saat dilimi |
| `test_booking_login_resume` | ★ misafir kilidi girişten sonra da geçerli (`viewer_key` değişmez), kilit sahipliği üye bazında korunur, `CUSTOMER_OVERLAP`, istemcinin gönderdiği `shadowParentId` doğrulanmadan kaydedilmez |

Testler ayrı bir PostgreSQL veritabanı kullanır (varsayılan: Docker'daki
`aurora_test`); geliştirme veritabanı (`aurora`) etkilenmez. Başka bir
adres için `TEST_DATABASE_URL` verilebilir. Test başında o veritabanındaki
**tüm tablolar** silinir; bu yüzden adı `_test` ile bitmeyen bir
veritabanında testler çalışmayı reddeder.

---

## Next.js sürümünden farklar

Karşılaştırma, orijinal `Vanccha/beauty_center_system` reposunadır — bu
depodaki arayüz (`../frontend/`) zaten bu FastAPI sunucusunu kullanır.

| Konu | Next.js sürümü (Prisma) | Bu sürüm |
|---|---|---|
| Randevu akışındaki üç hata | var | **düzeltildi** (§ Düzeltilen hatalar) |
| Müsaitlik ucu | ziyaretçiyi tanımıyor | `viewer_key` ile kendi kilidini tanır |
| Açık kilidi sorgulama | yok | `GET /api/slots/lock/active` |
| Vitrin verisi | sunucu bileşenlerinde (SSR), doğrudan Prisma sorgusu | `GET /api/showcase` tek uçta |
| Panel özeti | sayfa içinde sorgu | `GET /api/admin/dashboard` |
| Veritabanı erişimi | arayüz doğrudan Prisma'ya bağlı | arayüz (`../frontend/`) veritabanına hiç dokunmaz, yalnızca bu API ile konuşur |
| Fotoğraf indirme betiği | `npm run photos` | aynı — `cd frontend && npm run photos` (Unsplash → `frontend/public/photos/`) |

Arayüz bu depoda `../frontend/` altında yaşar ve `heldByYou`, `yourLock`,
`package.isNominal` gibi bu backend'e özgü yeni alanları kullanır (bkz.
§ Düzeltilen hatalar → arayüz tarafı). `frontend/next.config.mjs`,
`/api/*` ve `/uploads/*` isteklerini `API_URL` ortam değişkenine
(varsayılan `http://127.0.0.1:8000`) proxy'ler; arayüz kendisi hiçbir
zaman veritabanına veya başka bir servise doğrudan bağlanmaz. Arayüze özgü
ayrıntılar (rota haritası, API istemcileri, randevu akışı) için bkz.
[`../frontend/README.md`](../frontend/README.md).

## Ortam değişkenleri

Tümünün lokal çalışan bir varsayılanı vardır; `.env` olmadan da proje ayağa
kalkar.

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `APP_ENV` | `development` | `development` / `test` dışındaki **her değer üretim sayılır**: `devCode` dönmez, çerezler `secure`, `/docs` ve demo sayfası kapalı, sırlar zorunlu |
| `DATABASE_URL` | lokal PostgreSQL (`aurora@localhost:5432/aurora`) | Yalnızca PostgreSQL kabul edilir; `postgres://…` adresleri otomatik olarak psycopg sürücüsüne çevrilir. Üretimde zorunlu |
| `SESSION_SECRET` | lokal sabit | Oturum anahtarı — üretimde zorunlu, ≥32 karakter |
| `PHONE_HASH_SECRET` | lokal sabit | Risk havuzu HMAC anahtarı — üretimde zorunlu, ≥32 karakter. **Değiştirilirse geçmiş risk kayıtları eşleşmez** |
| `CRON_SECRET` | boş | `/api/cron/sweep` için `X-Cron-Secret` başlığı — üretimde zorunlu, ≥32 karakter |
| `APP_TIMEZONE` | `Europe/Istanbul` | Tüm "şimdi" hesapları bu saat dilimine göre yapılır |
| `CORS_ORIGINS` | geliştirmede `localhost:3000`, üretimde boş | Tarayıcı API'ye doğrudan bağlanacaksa izinli origin'ler (virgülle) |
| `SLOT_LOCK_TTL_SECONDS` | `300` | Soft-lock ömrü |
| `SLOT_GRID_MINUTES` | `15` | Slot tarama adımı |
| `NOTIFICATION_DRIVER` | `console` | `console` (log) veya `evolution` (WhatsApp). Tanınmayan değerde uygulama başlamaz |
| `EVOLUTION_API_URL` / `EVOLUTION_API_KEY` / `EVOLUTION_INSTANCE` | boş | `evolution` sürücüsü için zorunlu |
| `WHATSAPP_COUNTRY_CODE` | `90` | Numaralara eklenen ülke kodu |
| `WHATSAPP_SEND_INTERVAL_MS` | `1500` | Kuyruk mesajları arası bekleme |
| `NOTIFICATION_BATCH_SIZE` | `20` | Bir bakım çalıştırmasında en fazla mesaj |
| `EVOLUTION_WEBHOOK_URL` | boş | Evolution'ın backend'e ulaştığı adres; boşsa karşılama çalışmaz |
| `EVOLUTION_WEBHOOK_SECRET` | geliştirmede lokal sabit | Webhook doğrulama anahtarı (üretimde ≥32 karakter) |
| `PUBLIC_SITE_URL` | `http://localhost:3000` | Müşteriye giden bağlantılar |
| `DEV_OTP_CODE` | boş | Doluysa geliştirmede sabit kod; üretimde tanımlıysa uygulama başlamaz |
| `UPLOAD_DIR` | `./uploads` | Yüklenen görsellerin kök klasörü |

## WhatsApp bildirimleri (Evolution API)

OTP kodları ve randevu hatırlatmaları WhatsApp üzerinden,
[Evolution API](https://doc.evolution-api.com) ile gönderilir. Numara QR
kodla bağlanır (Baileys); Meta'nın ücretli Cloud API'si **kullanılmaz**.

```bash
docker compose --profile whatsapp up -d     # PostgreSQL + Evolution API (localhost:8080)
# .env:
NOTIFICATION_DRIVER=evolution
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=aurora-lokal-evolution-anahtari
EVOLUTION_INSTANCE=aurora

# Numarayı bağlamak için: admin paneli > WhatsApp (💬) > "QR kodu ile bağla" (OWNER)
# ya da komut satırından:
python -m app.whatsapp connect              # whatsapp-qr.png üretir; telefonla okut
python -m app.whatsapp status               # "open" görünmeli
python -m app.whatsapp test 5321234567      # deneme mesajı
```

Davranış:

- **OTP:** gönderimden önce bağlantı durumu kontrol edilir. Numara bağlı
  değilse istek hemen `503 DELIVERY_FAILED` döner ve müşterinin kod isteme
  hakkından düşmez. Evolution API bağlı olmayan instance'a gönderilen
  mesajda hata vermek yerine uzun süre asılı kaldığı için bu kontrol
  gereklidir. Gönderim başarısız olursa `502 DELIVERY_FAILED` döner.
- **Kuyruk** (`/api/cron/sweep`): kayıtlar önce sahiplenilir (`SENDING`,
  PostgreSQL'de `FOR UPDATE SKIP LOCKED`), gönderim transaction dışında
  yapılır. Başarısız mesaj 5, 10, 20, 40 dakika arayla yeniden denenir,
  5. denemede `FAILED` olur. Bağlantı kopuksa hiç deneme yapılmaz,
  denemeler harcanmaz. Mesajlar arasında `WHATSAPP_SEND_INTERVAL_MS`
  kadar beklenir.
- **Panel:** `/admin/whatsapp` sayfası durumu gösterir; salon sahibi QR'ı
  ekranda okutur veya bağlantıyı keser. Bağlantı koptuğunda panelin her
  sayfasında uyarı çıkar. Uçlar: `GET /api/admin/messaging/status`
  (MANAGER+), `POST /api/admin/messaging/qr` ve `.../logout` (OWNER).
- **İlk mesajda karşılama:** Salona ilk kez yazan kişiye otomatik mesaj
  gider (panelden açılır/kapanır, metin düzenlenir). Sistemin veya
  personelin daha önce yazıştığı kişilere, numara bağlanırken sohbet
  geçmişi olanlara, gruplara ve 10 dakikadan eski mesajlara gitmez.
  Evolution gelen mesajları `POST /api/webhooks/evolution?token=…` ucuna
  bildirir; webhook backend açılırken ve QR istenirken kendiliğinden
  kurulur (`EVOLUTION_WEBHOOK_URL` gerekir). Ayrıntı:
  `app/services/whatsapp_inbound.py`.

Riskler ve öneriler:

- QR ile bağlanan numara resmi bir entegrasyon değildir. WhatsApp numarayı
  kısıtlayabilir veya kapatabilir. Salonun ana numarasını değil, **ayrı bir
  numara** kullanın.
- Yalnızca bilgilendirme mesajı (kod, hatırlatma) gönderin. Toplu kampanya
  mesajı bu numaradan gönderilmemelidir; ticari ileti için müşterinin açık
  onayı da gerekir.
- Telefon uzun süre internetsiz kalırsa veya bağlı cihaz kaldırılırsa
  bağlantı düşer: `status` "open" değilse `connect` ile QR yeniden okutulur.
- Evolution API'nin oturum dosyaları `evolution_instances` volume'unda
  tutulur; silinirse QR yeniden okutulmalıdır.
- Üretimde Evolution API'yi dışarıya açmayın (yalnızca backend erişsin) ve
  `AUTHENTICATION_API_KEY` için güçlü, rastgele bir anahtar kullanın.

## Üretime alma

```bash
docker build -t aurora-api .
docker run -p 8000:8000   -e DATABASE_URL=postgresql+psycopg://…   -e SESSION_SECRET=… -e PHONE_HASH_SECRET=… -e CRON_SECRET=…   -e FORWARDED_ALLOW_IPS=<ters proxy IP'si>   -v aurora-uploads:/data/uploads   aurora-api
```

- İmajda `APP_ENV=production` varsayılandır; sırlar eksikse uygulama başlamaz.
  Sır üretmek için: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- Konteyner açılışta `alembic upgrade head` çalıştırır, sonra uvicorn'u başlatır.
- Birden fazla worker/sunucu çalışabilir: deneme sınırları ve kilitler
  veritabanında tutulur.
- `--proxy-headers` açıktır; deneme sınırlarının gerçek istemci IP'sini
  görmesi için `FORWARDED_ALLOW_IPS` ters proxy'nin adresi olmalıdır.
- Bakım işi için bir zamanlayıcı (ör. 5 dakikada bir):
  `curl -X POST -H "X-Cron-Secret: $CRON_SECRET" https://…/api/cron/sweep`
- `python -m app.seed` üretimde çalışmayı reddeder (veritabanını sıfırlar).

## Kapsam dışı

| Özellik | Durum |
|---|---|
| SMS gönderimi | ⬚ yok — mesajlar WhatsApp üzerinden gider (aşağıya bakınız) |
| Kampanya mesajlarının toplu gönderimi | ⬚ bilerek yok — QR ile bağlı numarada toplu gönderim numaranın kısıtlanma riskini artırır |
| Zamanlanmış görev (cron) | ⬚ **iskelet** — `/api/cron/sweep` bir zamanlayıcıdan `X-Cron-Secret` başlığıyla ya da panelden (MANAGER+) tetiklenir; doğruluk buna bağlı değil |
| Ödeme / ön ödeme tahsilatı | ⬚ kapsam dışı (risk skoru "ön ödeme iste" önerisi üretir, tahsilat yok) |
| Çok şube | ⬚ veri modeli hazır; `get_default_branch()` tek değişim noktası |
| Personel/hizmet CRUD ekranları | ⬚ seed ile geliyor; API deseni hazır |
