import { ArrowRight, Clock, Droplets, FlaskConical, Plus, Sparkles, Star } from 'lucide-react';
import Link from 'next/link';

import { ReviewCard } from '@/components/marketing/ReviewCard';
import { Stars } from '@/components/marketing/Stars';
import { durationLabel, formatTl } from '@/lib/api-client';
import { resolveHeroImage } from '@/lib/hero-image';
import { serverApi, type MeResponse, type PublicReview, type ReviewSummary } from '@/lib/server-api';
import { photo, photoOrFallback } from '@/lib/site-photos';
import { minutesToLabel } from '@/lib/time';
import { CategoryIcon } from '@/components/marketing/CategoryIcon';

export const dynamic = 'force-dynamic';

/** `GET /api/showcase` yanıtı — açılış sayfasının tüm verisi tek istekte. */
interface Showcase {
  salon: {
    branchId: number;
    salonName: string;
    branchName: string;
    phone: string | null;
    address: string | null;
  };
  stats: {
    completedAppointments: number;
    servedCustomers: number;
    returningRate: number;
    staffCount: number;
    portfolioCount: number;
  };
  openingHours: {
    weekday: number;
    label: string;
    isToday: boolean;
    range: { startMin: number; endMin: number } | null;
  }[];
  categories: {
    id: number;
    name: string;
    slug: string;
    icon: string | null;
    fromPrice: number | null;
    serviceCount: number;
    cover: string | null;
  }[];
  services: {
    id: number;
    categoryId: number | null;
    categoryName: string;
    name: string;
    description: string | null;
    price: number;
    passiveMin: number;
    totalMin: number;
  }[];
  reviews: { summary: ReviewSummary; items: PublicReview[] };
  team: {
    id: number;
    name: string;
    role: string;
    photoUrl: string | null;
    rating: { average: number; count: number } | null;
    specialties: string[];
  }[];
  portfolio: {
    id: number;
    title: string;
    description: string | null;
    imageUrl: string;
    categoryId: number | null;
  }[];
}

/**
 * ====================================================================
 * AÇILIŞ SAYFASI — önce vitrin, sonra randevu
 * ====================================================================
 *
 * Bu sayfa bir randevu formu DEĞİLDİR. Görevi, salonu tanıtmak ve
 * ziyaretçiyi ikna etmektir; randevu adımı ancak ikna olduktan sonra
 * gelir. Bu yüzden sayfa yukarıdan aşağıya bir satış hikâyesi izler:
 *
 *   1. Kahraman        — tam ekran fotoğraf, tek cümlelik vaat
 *   2. Güven şeridi    — gerçek sayılar (uydurma değil, DB'den)
 *   3. Kategoriler     — "ne yaptırmak istersin?"
 *   4. Kalite sözü     — işi nasıl yaptığımız
 *   5. Hizmetler       — vitrin hizmetleri, süre ve fiyatla
 *   6. Yorumlar        — sosyal kanıt (Review tablosu)
 *   7. Ekip            — arkasındaki insanlar
 *   8. Galeri          — yapılmış işler
 *   9. Ziyaret         — saatler, adres, telefon
 *  10. SSS + kapanış çağrısı
 *
 * DÜRÜSTLÜK KURALI: sayfadaki her rakam veritabanından sayılır. Yorum
 * yoksa yorum bölümü, iş yoksa galeri bölümü hiç render edilmez —
 * boş bir vitrin, sahte bir vitrinden iyidir.
 *
 * Üye girişi varsa kahraman metni kişiselleştirilir; metin uydurulmaz,
 * son tamamlanmış randevu ve o hizmetin `recommendedRepeatDays`
 * değerinden üretilir (`buildWelcome`).
 */
export default async function HomePage() {
  // Veri FastAPI backend'inden gelir; bu sayfa veritabanını bilmez.
  const [showcase, me] = await Promise.all([
    serverApi<Showcase>('/api/showcase'),
    serverApi<MeResponse>('/api/me'),
  ]);

  const welcome = me.welcome;
  const stats = showcase.stats;
  const openingHours = showcase.openingHours;
  const portfolio = showcase.portfolio;
  const staff = showcase.team;
  const reviews = showcase.reviews.items;
  const reviewSummary = showcase.reviews.summary;

  // JSX aynı kalsın diye salon bilgisi eski biçimde paketlenir.
  const branch = {
    name: showcase.salon.branchName,
    address: showcase.salon.address,
    salon: { name: showcase.salon.salonName, phone: showcase.salon.phone },
  };

  // --- Kategori kartları: kapak görseli o kategorinin ilk işinden gelir ---
  const categoryCards = showcase.categories.map((category) => ({
    ...category,
    cover: photo(`kategori-${category.slug}.jpg`) ?? category.cover,
  }));

  // --- Vitrin hizmetleri: en pahalı 6 hizmet (salonun "imza" işleri) ---
  const featuredServices = showcase.services.slice(0, 6);

  // Büyük açılış görseli: salonun kendi fotoğrafı > vitrin fotoğrafı > illüstrasyon.
  const hero = resolveHeroImage();

  const openToday = openingHours.find((row) => row.isToday);

  return (
    <div>
      {/* ================================================================
          1. KAHRAMAN — sayfa metinle değil, fotoğrafla açılır
          ============================================================ */}
      <section className="relative flex min-h-[92svh] items-end overflow-hidden md:min-h-[88svh]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={hero.url}
          alt=""
          aria-hidden
          className="absolute inset-0 h-full w-full object-cover"
        />

        {/*
          Okunabilirlik katmanı: üstte hafif (fotoğraf görünsün), altta
          koyu (metin her zaman okunsun). Tek bir düz siyah katman
          fotoğrafı öldürürdü.
        */}
        <div
          aria-hidden
          className="absolute inset-0 bg-gradient-to-b from-ink-900/55 via-ink-900/30 to-ink-900/90"
        />

        <div className="bleed relative pb-12 pt-28 text-white md:pb-16 md:pt-32">
          {welcome ? (
            <>
              <p className="eyebrow !text-brass-300">{branch.salon.name}</p>
              <h1 className="display mt-4 max-w-3xl text-4xl font-light leading-[1.05] md:text-7xl">
                {welcome.headline}
              </h1>
              {welcome.subline && (
                <p className="mt-4 max-w-xl text-base text-white/85 md:text-lg">
                  {welcome.subline}
                </p>
              )}

              {welcome.upcoming && (
                <div className="mt-6 inline-flex flex-wrap items-center gap-2 rounded-[2px] border border-white/25 bg-white/10 px-4 py-3 text-sm backdrop-blur">
                  <span className="font-semibold">Yaklaşan randevun</span>
                  <span className="text-white/85">
                    {welcome.upcoming.dateLabel} · {minutesToLabel(welcome.upcoming.startMin)} ·{' '}
                    {welcome.upcoming.serviceNames.join(' + ')} ({welcome.upcoming.staffName})
                  </span>
                </div>
              )}

              <div className="mt-7 flex flex-wrap gap-3">
                {welcome.repeatServiceIds.length > 0 && (
                  <Link
                    href={`/randevu?services=${welcome.repeatServiceIds.join(',')}`}
                    className="btn-light"
                  >
                    {welcome.isDue ? 'Aynısını tekrar al' : 'Yine aynısını al'}
                  </Link>
                )}
                <Link href="/randevu" className="btn-outline-light">
                  Yeni randevu
                </Link>
              </div>
            </>
          ) : (
            <>
              <p className="eyebrow !text-brass-300">Kadıköy · {branch.name}</p>
              <h1 className="display mt-4 max-w-3xl text-4xl font-light leading-[1.05] md:text-7xl">
                Kendine ayırdığın zaman,
                <br />
                işini bilen ellerde.
              </h1>
              <p className="mt-5 max-w-xl text-base leading-relaxed text-white/85 md:text-lg">
                {branch.salon.name} — saç, tırnak, kaş ve cilt bakımında {stats.staffCount} uzman.
                Uygun saatleri üye olmadan gör; randevu için tek adımlık telefon doğrulaması
                yeterli.
              </p>

              <div className="mt-8 flex flex-wrap items-center gap-3">
                <Link href="/randevu" className="btn-light group">
                  Uygun saatleri gör
                  <ArrowRight size={16} strokeWidth={1.5} aria-hidden className="transition-transform duration-300 group-hover:translate-x-[3px]" />
                </Link>
                <Link href="/portfolyo" className="btn-outline-light">
                  İşlerimize bak
                </Link>
              </div>
            </>
          )}

          {/*
            Kahramanın altındaki şerit: puan + bugünün saatleri + adres.
            Puan yalnızca gerçek yorum varsa gösterilir.
          */}
          <dl className="mt-12 flex flex-wrap gap-x-12 gap-y-4 border-t border-white/20 pt-6 text-sm text-white/80">
            {reviewSummary.average !== null && (
              <div>
                <dt className="text-[11px] uppercase tracking-[0.14em] text-white/60">Müşteri puanı</dt>
                <dd className="mt-1 flex items-center gap-2 font-medium text-white">
                  <Stars value={reviewSummary.average} size="sm" />
                  {reviewSummary.average.toFixed(1).replace('.', ',')}
                  <span className="text-white/60">({reviewSummary.count} yorum)</span>
                </dd>
              </div>
            )}
            <div>
              <dt className="text-[11px] uppercase tracking-[0.14em] text-white/60">Bugün</dt>
              <dd className="mt-1 font-medium text-white">
                {openToday?.range
                  ? `${minutesToLabel(openToday.range.startMin)} – ${minutesToLabel(openToday.range.endMin)}`
                  : 'Kapalı'}
              </dd>
            </div>
            <div>
              <dt className="text-[11px] uppercase tracking-[0.14em] text-white/60">Adres</dt>
              <dd className="mt-1 font-medium text-white">{branch.address}</dd>
            </div>
          </dl>
        </div>
      </section>

      {/* ================================================================
          2. GÜVEN ŞERİDİ — her rakam veritabanından sayılır
          ============================================================ */}
      <section className="border-b border-sand-200 bg-white">
        <dl className="bleed grid grid-cols-2 gap-6 py-10 md:grid-cols-4 md:py-14">
          {[
            {
              value: stats.completedAppointments.toLocaleString('tr-TR'),
              label: 'tamamlanan randevu',
              show: stats.completedAppointments > 0,
            },
            {
              value: stats.servedCustomers.toLocaleString('tr-TR'),
              label: 'hizmet verdiğimiz müşteri',
              show: stats.servedCustomers > 0,
            },
            {
              value: `%${Math.round(stats.returningRate * 100)}`,
              label: 'tekrar gelen müşteri',
              show: stats.servedCustomers >= 5,
            },
            {
              value: reviewSummary.average
                ? reviewSummary.average.toFixed(1).replace('.', ',')
                : '—',
              label: `ortalama puan (${reviewSummary.count} yorum)`,
              show: reviewSummary.count > 0,
            },
          ]
            .filter((item) => item.show)
            .map((item) => (
              <div key={item.label}>
                <dt className="sr-only">{item.label}</dt>
                <dd>
                  <span className="display block text-3xl font-light tabular-nums text-plum-700 md:text-5xl">
                    {item.value}
                  </span>
                  <span className="mt-1 block text-sm text-ink-500">{item.label}</span>
                </dd>
              </div>
            ))}
        </dl>
      </section>

      {/* ================================================================
          3. KATEGORİLER
          ============================================================ */}
      <section className="bleed py-20 md:py-28">
        <p className="eyebrow reveal">Hizmetlerimiz</p>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <h2 className="display reveal text-3xl md:text-5xl">Ne yaptırmak istersin?</h2>
          <Link href="/randevu" className="btn-link group">
            Tüm hizmetler ve fiyatlar
            <ArrowRight size={16} strokeWidth={1.5} aria-hidden className="transition-transform duration-300 group-hover:translate-x-[3px]" />
          </Link>
        </div>

        <div className="mt-10 grid grid-cols-2 gap-3 md:mt-14 md:grid-cols-4 md:gap-5">
          {categoryCards.map((category) => (
            <Link
              key={category.id}
              href={`/randevu?category=${category.slug}`}
              className="group relative aspect-[3/4] overflow-hidden rounded-[4px] border border-sand-200"
            >
              {category.cover ? (
                /* eslint-disable-next-line @next/next/no-img-element */
                <img
                  src={category.cover}
                  alt=""
                  aria-hidden
                  className="absolute inset-0 h-full w-full object-cover transition-transform duration-700 group-hover:scale-[1.03]"
                />
              ) : (
                <div aria-hidden className="absolute inset-0 bg-plum-500" />
              )}

              <div
                aria-hidden
                className="absolute inset-0 bg-gradient-to-t from-ink-900/90 via-ink-900/25 to-transparent"
              />

              <div className="absolute inset-x-0 bottom-0 p-3 text-white md:p-4">
                <p className="display text-lg leading-tight md:text-xl">
                  <CategoryIcon slug={category.slug} size={18} className="mr-2 inline-block align-[-2px] text-brass-300" />
                  {category.name}
                </p>
                <p className="mt-1 text-xs text-white/80">
                  {category.serviceCount} hizmet
                  {category.fromPrice !== null && ` · ${formatTl(category.fromPrice)}'den`}
                </p>
              </div>
            </Link>
          ))}
        </div>
      </section>

      {/* ================================================================
          4. KALİTE SÖZÜ — "iyi salon" iddiası değil, çalışma biçimi
          ============================================================ */}
      <section className="bg-white py-20 md:py-28">
        <div className="bleed grid gap-12 md:grid-cols-2 md:items-center md:gap-14">
          <div>
            <p className="eyebrow">Kalite sözümüz</p>
            <h2 className="display reveal mt-3 text-3xl md:text-5xl">
              İyi iş, iyi malzeme ve dürüst bir saat.
            </h2>
            <p className="muted mt-4 max-w-lg leading-relaxed">
              Bir bakım randevusunun en sinir bozucu tarafı belirsizliktir: ne kadar süreceği,
              ne kadar tutacağı, sıranın ne zaman geleceği. Biz bu üçünü de baştan söylüyoruz.
            </p>

            <ul className="mt-10 space-y-6">
              {[
                {
                  icon: Clock,
                  title: 'Randevun dakikası dakikasına planlanır',
                  body: 'Birden fazla hizmet seçtiğinde takvimde tek blok açılır; işlemler arka arkaya dizilir, boşta beklemezsin.',
                },
                {
                  icon: Droplets,
                  title: 'Bekleme süren bize yazılır, sana değil',
                  body: 'Boya beklemesi gibi pasif süreler ustanın takviminde ayrı işaretlenir. Bu sayede kimse "boya bekliyor" diye kapıda tutulmaz.',
                },
                {
                  icon: FlaskConical,
                  title: 'Alerji ve hassasiyet kaydın dosyanda durur',
                  body: 'Bir kez söylediğin hassasiyet her randevuda ustanın ekranında çıkar. Gerekiyorsa patch testi biz hatırlatırız.',
                },
                {
                  icon: Sparkles,
                  title: 'Tek kullanımlık malzeme, sterilize alet',
                  body: 'Törpü ve benzeri malzemeler tek kullanımlıktır; metal aletler her müşteriden sonra sterilizasyondan geçer.',
                },
              ].map((item) => (
                <li key={item.title} className="flex gap-4">
                  <span
                    aria-hidden
                    className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-brass-300 text-brass-700"
                  >
                    <item.icon size={18} strokeWidth={1.5} />
                  </span>
                  <div>
                    <p className="font-semibold">{item.title}</p>
                    <p className="muted mt-1 leading-relaxed">{item.body}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>

          {/* Mekân kolajı — "burası neresi?" sorusuna görsel cevap */}
          <div className="grid grid-cols-2 gap-3 md:gap-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={photoOrFallback('interior-1.jpg', 'hero.jpg')}
              alt="Salonun çalışma alanı"
              loading="lazy"
              className="col-span-2 h-56 w-full rounded-[2px] object-cover md:h-72"
            />
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={photoOrFallback('detay-firca.jpg', 'interior-2.jpg')}
              alt="Kullandığımız fırça ve malzemeler"
              loading="lazy"
              className="h-40 w-full rounded-[2px] object-cover md:h-48"
            />
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={photoOrFallback('interior-2.jpg', 'interior-3.jpg')}
              alt="Salon iç mekânı"
              loading="lazy"
              className="h-40 w-full rounded-[2px] object-cover md:h-48"
            />
          </div>
        </div>
      </section>

      {/* ================================================================
          5. VİTRİN HİZMETLERİ — süre ve fiyat açıkça yazılır
          ============================================================ */}
      <section className="bleed py-20 md:py-28">
        <p className="eyebrow reveal">Öne çıkanlar</p>
        <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
          <h2 className="display reveal text-3xl md:text-5xl">İmza hizmetlerimiz</h2>
          <p className="muted">Süreler ustanın hızına göre değişebilir; fiyatlar sabittir.</p>
        </div>

        <ul className="mt-10 border-t border-sand-200 md:mt-14">
          {featuredServices.map((service) => (
            <li key={service.id} className="border-b border-sand-200">
              <Link
                href={`/randevu?services=${service.id}`}
                className="group flex items-start justify-between gap-6 py-6 transition-colors hover:bg-white/60 md:px-2"
              >
                <div className="min-w-0">
                  <p className="eyebrow">{service.categoryName}</p>
                  <p className="display mt-1.5 text-xl md:text-2xl">{service.name}</p>
                  {service.description && (
                    <p className="muted mt-1.5 max-w-xl leading-relaxed">{service.description}</p>
                  )}
                  <p className="mt-3 text-xs tabular-nums text-ink-500">
                    Yaklaşık {durationLabel(service.totalMin)}
                    {service.passiveMin > 0 &&
                      ` · ${durationLabel(service.passiveMin)} işlem beklemesi dahil`}
                  </p>
                </div>
                <span className="flex shrink-0 items-center gap-3 text-base font-medium tabular-nums text-ink-900 md:text-lg">
                  {formatTl(service.price)}
                  <ArrowRight size={16} strokeWidth={1.5} aria-hidden className="text-ink-300 transition-transform duration-300 group-hover:translate-x-[3px] group-hover:text-plum-600" />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      {/* ================================================================
          6. YORUMLAR — sosyal kanıt, tamamı gerçek randevulardan
          ============================================================ */}
      {reviewSummary.count > 0 && reviewSummary.average !== null && (
        <section className="bg-sand-100 py-20 md:py-28">
          <div className="bleed">
            <p className="eyebrow">Değerlendirmeler</p>
            <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
              <h2 className="display reveal text-3xl md:text-5xl">Müşterilerimiz ne diyor?</h2>
              <p className="muted">
                Tamamı, salonda hizmet almış müşteriler tarafından yazıldı.
              </p>
            </div>

            <div className="mt-10 grid gap-8 md:mt-14 md:grid-cols-[minmax(0,320px)_1fr] md:items-start md:gap-12">
              {/* Puan özeti */}
              <div className="rounded-[4px] border border-sand-200 bg-white p-6">
                <div className="flex items-baseline gap-2">
                  <span className="display text-5xl font-light tabular-nums text-plum-700">
                    {reviewSummary.average.toFixed(1).replace('.', ',')}
                  </span>
                  <span className="text-sm text-ink-500">/ 5</span>
                </div>
                <Stars value={reviewSummary.average} size="lg" className="mt-2" />
                <p className="muted mt-2">
                  {reviewSummary.count} değerlendirme ·{' '}
                  <span className="font-medium text-ink-700">
                    %{Math.round(reviewSummary.positiveRate * 100)}
                  </span>{' '}
                  dört yıldız ve üzeri
                </p>

                {/* Yıldız dağılımı — dürüstlük göstergesi */}
                <ul className="mt-5 space-y-1.5">
                  {([5, 4, 3, 2, 1] as const).map((star) => {
                    const value = reviewSummary.distribution[star];
                    const ratio = reviewSummary.count ? (value / reviewSummary.count) * 100 : 0;
                    return (
                      <li key={star} className="flex items-center gap-2 text-xs text-ink-500">
                        <span className="w-3 tabular-nums">{star}</span>
                        <Star size={12} strokeWidth={1.5} aria-hidden className="fill-brass-500 text-brass-500" />
                        <span
                          aria-hidden
                          className="h-1 flex-1 overflow-hidden bg-sand-100"
                        >
                          <span
                            className="block h-full bg-plum-600"
                            style={{ width: `${ratio}%` }}
                          />
                        </span>
                        <span className="w-6 text-right tabular-nums">{value}</span>
                      </li>
                    );
                  })}
                </ul>

                <p className="mt-5 text-xs leading-relaxed text-ink-500">
                  Yorumlar yalnızca tamamlanmış randevusu olan müşteriler tarafından yazılır.
                </p>

                <Link href="/yorumlar" className="btn-secondary mt-4 w-full">
                  Tüm yorumları oku
                </Link>
              </div>

              {/* Yorum kartları */}
              <ul className="grid gap-3 sm:grid-cols-2 md:gap-4">
                {reviews.map((review) => (
                  <li key={review.id}>
                    <ReviewCard review={review} />
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </section>
      )}

      {/* ================================================================
          7. EKİP
          ============================================================ */}
      <section className="bleed py-20 md:py-28">
        <p className="eyebrow reveal">Ekibimiz</p>
        <h2 className="display reveal mt-3 text-3xl md:text-5xl">İşi yapan eller</h2>
        <p className="muted mt-3 max-w-xl">
          Randevu alırken ustanı kendin seçebilirsin. Puanlar yalnızca en az üç yorum almış
          ustalar için gösterilir.
        </p>

        <ul className="mt-10 grid gap-5 sm:grid-cols-2 md:mt-14 lg:grid-cols-4">
          {staff.map((member, index) => {
            const rating = member.rating;
            // Uzmanlık: verdiği hizmetlerden ilk üçü (backend hazırlar).
            const specialties = member.specialties;
            const roleLabel =
              member.role === 'OWNER'
                ? 'Kurucu · Saç tasarımı'
                : member.role === 'MANAGER'
                  ? 'Salon yöneticisi'
                  : 'Uzman';

            return (
              <li
                key={member.id}
                className="group overflow-hidden rounded-[4px] border border-sand-200 bg-white"
              >
                <div className="aspect-[4/5] w-full overflow-hidden bg-sand-100">
                  {member.photoUrl ? (
                    /* eslint-disable-next-line @next/next/no-img-element */
                    <img
                      src={member.photoUrl}
                      alt={member.name}
                      loading={index < 2 ? 'eager' : 'lazy'}
                      className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-[1.03]"
                    />
                  ) : (
                    <span className="grid h-full w-full place-items-center font-[family-name:var(--font-display)] text-4xl text-ink-500">
                      {member.name[0]}
                    </span>
                  )}
                </div>

                <div className="p-4">
                  <p className="display text-lg leading-tight">{member.name}</p>
                  <p className="eyebrow mt-1.5 !text-[10px]">{roleLabel}</p>

                  {rating && (
                    <p className="mt-2 flex items-center gap-1.5 text-xs text-ink-500">
                      <Stars value={rating.average} size="sm" />
                      {rating.average.toFixed(1).replace('.', ',')} ({rating.count})
                    </p>
                  )}

                  {specialties.length > 0 && (
                    <p className="muted mt-2 leading-relaxed">{specialties.join(' · ')}</p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      {/* ================================================================
          8. GALERİ
          ============================================================ */}
      {portfolio.length > 0 && (
        <section className="bg-white py-20 md:py-28">
          <div className="bleed">
            <p className="eyebrow reveal">Portfolyo</p>
            <div className="mt-3 flex flex-wrap items-end justify-between gap-4">
              <h2 className="display reveal text-3xl md:text-5xl">Son işlerimiz</h2>
              <Link href="/portfolyo" className="btn-link group">
                Tüm galeri ({stats.portfolioCount})
                <ArrowRight size={16} strokeWidth={1.5} aria-hidden className="transition-transform duration-300 group-hover:translate-x-[3px]" />
              </Link>
            </div>

            <div className="mt-10 grid grid-cols-2 gap-3 md:mt-14 md:grid-cols-4 md:gap-4">
              {portfolio.slice(0, 8).map((item) => (
                <Link
                  key={item.id}
                  href="/portfolyo"
                  className="group relative aspect-square overflow-hidden rounded-[4px] border border-sand-200"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={item.imageUrl}
                    alt={item.title}
                    loading="lazy"
                    className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-[1.03]"
                  />
                  <div
                    aria-hidden
                    className="absolute inset-0 bg-gradient-to-t from-ink-900/85 via-transparent to-transparent opacity-0 transition-opacity group-hover:opacity-100"
                  />
                  <p className="absolute inset-x-0 bottom-0 truncate p-3 text-xs font-medium text-white opacity-0 transition-opacity group-hover:opacity-100">
                    {item.title}
                  </p>
                </Link>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ================================================================
          9. ZİYARET — saatler, adres, telefon
          ============================================================ */}
      <section className="bleed py-20 md:py-28">
        <div className="grid gap-10 md:grid-cols-2 md:items-center md:gap-16">
          <div className="order-2 md:order-1">
            <p className="eyebrow reveal">Bize gel</p>
            <h2 className="display reveal mt-3 text-3xl md:text-5xl">{branch.name}</h2>
            <p className="muted mt-3">{branch.address}</p>

            <dl className="mt-6 divide-y divide-sand-200 border-y border-sand-200">
              {openingHours.map((row) => (
                <div
                  key={row.weekday}
                  className={`flex items-center justify-between py-3 text-sm tabular-nums ${
                    row.isToday ? 'font-semibold text-plum-700' : 'text-ink-700'
                  }`}
                >
                  <dt>
                    {row.label}
                    {row.isToday && <span className="ml-2 text-xs font-normal">(bugün)</span>}
                  </dt>
                  <dd className={row.range ? '' : 'text-ink-500'}>
                    {row.range
                      ? `${minutesToLabel(row.range.startMin)} – ${minutesToLabel(row.range.endMin)}`
                      : 'Kapalı'}
                  </dd>
                </div>
              ))}
            </dl>

            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/randevu" className="btn-primary">
                Randevu al
              </Link>
              {branch.salon.phone && (
                <a href={`tel:0${branch.salon.phone}`} className="btn-secondary">
                  0{branch.salon.phone}
                </a>
              )}
            </div>
          </div>

          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={photoOrFallback('interior-3.jpg', 'interior-1.jpg', 'hero.jpg')}
            alt="Salonun içi"
            loading="lazy"
            className="order-1 h-64 w-full rounded-[2px] object-cover md:order-2 md:h-[26rem]"
          />
        </div>
      </section>

      {/* ================================================================
          10. SIKÇA SORULANLAR
          ============================================================ */}
      <section className="bg-white py-20 md:py-28">
        <div className="bleed max-w-3xl">
          <p className="eyebrow reveal">Sıkça sorulanlar</p>
          <h2 className="display reveal mt-3 text-3xl md:text-5xl">Merak edilenler</h2>

          <div className="mt-10 divide-y divide-sand-200 border-y border-sand-200">
            {[
              {
                q: 'Randevu almak için üye olmam gerekiyor mu?',
                a: 'Uygun saatleri üye olmadan görebilirsin. Yalnızca randevuyu kesinleştirirken telefon numaranı doğrulaman gerekir — WhatsApp’tan gelen tek seferlik bir kod, şifre yok.',
              },
              {
                q: 'Birden fazla hizmeti aynı gün yaptırabilir miyim?',
                a: 'Evet. Seçtiğin hizmetler tek bir blok olarak planlanır; sistem bunları arka arkaya dizip toplam süreyi kısaltır. Örneğin manikür + kalıcı oje + nail art tek seansta tamamlanır.',
              },
              {
                q: 'Randevumu iptal edebilir veya değiştirebilir miyim?',
                a: 'Randevu Sorgula sayfasından yaklaşan randevunu görebilir ve iptal edebilirsin. Saat değişikliği için salonu araman yeterli — yerini birine kaptırmadan yeni saati ayarlarız.',
              },
              {
                q: 'Boya beklerken salonda ne kadar oturuyorum?',
                a: 'Boyanın işlem süresi randevuna dahildir ve önceden gösterilir. Bu süre boyunca ustan başka bir kısa işe geçebilir, ama senin saatin kaymaz.',
              },
              {
                q: 'Alerjim var, ne yapmalıyım?',
                a: 'Randevu notuna yazman yeterli; kaydın dosyana işlenir ve her randevuda ustanın ekranında görünür. Saç boyası gibi işlemlerde gerekiyorsa 48 saat önceden patch testi öneririz.',
              },
            ].map((item) => (
              <details key={item.q} className="group py-4">
                <summary className="flex cursor-pointer touch-target list-none items-center justify-between gap-4 font-medium">
                  {item.q}
                  <Plus
                    size={18}
                    strokeWidth={1.5}
                    aria-hidden
                    className="shrink-0 text-plum-600 transition-transform duration-300 group-open:rotate-45"
                  />
                </summary>
                <p className="muted mt-3 leading-relaxed">{item.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ================================================================
          11. KAPANIŞ ÇAĞRISI
          ============================================================ */}
      <section className="bleed py-20 md:py-28">
        <div className="relative overflow-hidden rounded-[4px]">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={photoOrFallback('detay-kozmetik.jpg', 'interior-2.jpg', 'hero.jpg')}
            alt=""
            aria-hidden
            loading="lazy"
            className="absolute inset-0 h-full w-full object-cover"
          />
          <div aria-hidden className="absolute inset-0 bg-ink-900/72" />

          <div className="relative px-6 py-20 text-center text-white md:py-28">
            <h2 className="display mx-auto max-w-xl text-3xl font-light leading-tight md:text-5xl">
              Uygun saatini şimdi seç
            </h2>
            <p className="mx-auto mt-4 max-w-md text-sm leading-relaxed text-white/85 md:text-base">
              Takvimi aç, sana uyan saati gör. Birden çok hizmet seçersen tek blok açılır ve
              daha erken çıkarsın.
            </p>
            <Link href="/randevu" className="btn-light group mt-8">
              Randevu al
              <ArrowRight size={16} strokeWidth={1.5} aria-hidden className="transition-transform duration-300 group-hover:translate-x-[3px]" />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
