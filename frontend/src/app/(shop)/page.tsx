import { ArrowRight, Clock, Droplets, FlaskConical, Plus, Sparkles, Star } from 'lucide-react';
import Link from 'next/link';

import { PortfolioGallery, type PortfolioCategory, type PortfolioItem } from '@/components/marketing/PortfolioGallery';
import { ReviewsBrowser } from '@/components/marketing/ReviewsBrowser';
import { Stars } from '@/components/marketing/Stars';
import { durationLabel, formatTl } from '@/lib/api-client';
import { resolveHeroImage } from '@/lib/hero-image';
import { serverApi, type MeResponse, type PublicReview, type ReviewSummary } from '@/lib/server-api';
import { photo, photoOrFallback } from '@/lib/site-photos';
import { minutesToLabel } from '@/lib/time';
import { ScrollCue } from './scroll-cue';
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
}

/** `GET /api/portfolio` yanıtı — kategori çipleri ve kategori/usta bilgili işler. */
interface PortfolioResponse {
  categories: PortfolioCategory[];
  items: PortfolioItem[];
}

/** `GET /api/reviews` yanıtı — özet her zaman tüm yorumları kapsar. */
interface ReviewsResponse {
  summary: ReviewSummary;
  items: PublicReview[];
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
 *   4. Hizmetler       — vitrin hizmetleri, süre ve fiyatla
 *   5. Portfolyo       — yapılmış işler (`#portfolyo`, sayfada filtrelenir)
 *   6. Yorumlar        — sosyal kanıt (`#yorumlar`, Review tablosu)
 *   7. Ekip            — arkasındaki insanlar
 *   8. Kalite sözü     — işi nasıl yaptığımız (kısa)
 *   9. Ziyaret         — saatler, adres, telefon
 *  10. SSS + kapanış çağrısı
 *
 * DÜRÜSTLÜK KURALI: sayfadaki her rakam veritabanından sayılır. Yorum
 * ve iş yoksa bölümler boş durum metni gösterir (bağlantı kopmasın);
 * uydurma içerik konmaz.
 *
 * Üye girişi varsa kahraman metni kişiselleştirilir; metin uydurulmaz,
 * son tamamlanmış randevu ve o hizmetin `recommendedRepeatDays`
 * değerinden üretilir (`buildWelcome`).
 */
export default async function HomePage() {
  // Veri FastAPI backend'inden gelir; bu sayfa veritabanını bilmez.
  const [showcase, me, portfolioData, reviewsData] = await Promise.all([
    serverApi<Showcase>('/api/showcase'),
    serverApi<MeResponse>('/api/me'),
    serverApi<PortfolioResponse>('/api/portfolio'),
    // Tüm yorumlar, tarih sırasıyla (eski /yorumlar sayfasındaki liste).
    serverApi<ReviewsResponse>('/api/reviews'),
  ]);

  const welcome = me.welcome;
  const stats = showcase.stats;
  const openingHours = showcase.openingHours;
  const staff = showcase.team;
  const reviewSummary = reviewsData.summary;
  const reviews = reviewsData.items;

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
      {/* İlk ekran: kahraman + güven şeridi birlikte ekranı TAM doldurur;
          sonraki bölüm ("Ne yaptırmak istersin?") ancak kaydırınca görünür.
          Mobilde alttaki sabit menünün (~63 px + güvenli alan) payı düşülür. */}
      <div className="flex min-h-[calc(100svh-63px-env(safe-area-inset-bottom))] flex-col lg:min-h-svh">
      {/* ================================================================
          1. KAHRAMAN — sayfa metinle değil, fotoğrafla açılır
          ============================================================ */}
      <section className="relative flex flex-1 items-end overflow-hidden">
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

        <div className="bleed relative pb-8 pt-24 text-white md:pb-10 md:pt-28 [@media(max-height:720px)]:pb-5 [@media(max-height:720px)]:pt-20">
          {welcome ? (
            <>
              <p className="eyebrow !text-brass-300">{branch.salon.name}</p>
              <h1 className="display mt-3 max-w-3xl text-3xl font-light leading-[1.08] md:text-6xl">
                {welcome.headline}
              </h1>
              {welcome.subline && (
                <p className="mt-3 max-w-xl text-base text-white/85 md:text-lg [@media(max-height:720px)]:hidden">
                  {welcome.subline}
                </p>
              )}

              {welcome.upcoming && (
                <div className="mt-5 inline-flex flex-wrap items-center gap-2 rounded-[2px] border border-white/25 bg-white/10 px-4 py-3 text-sm backdrop-blur">
                  <span className="font-semibold">Yaklaşan randevun</span>
                  <span className="text-white/85">
                    {welcome.upcoming.dateLabel} · {minutesToLabel(welcome.upcoming.startMin)} ·{' '}
                    {welcome.upcoming.serviceNames.join(' + ')} ({welcome.upcoming.staffName})
                  </span>
                </div>
              )}

              <div className="mt-5 flex flex-wrap gap-3">
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
              <h1 className="display mt-3 max-w-3xl text-3xl font-light leading-[1.08] md:text-6xl">
                Kendinize ayırdığınız
                <br />
                <em className="font-light italic text-brass-300">en güzel saat.</em>
              </h1>
              <p className="mt-4 max-w-xl text-base leading-relaxed text-white/85 md:text-lg [@media(max-height:720px)]:hidden">
                {branch.salon.name} — saç, tırnak, kaş ve cilt bakımında {stats.staffCount} uzman.
                Uygun saatleri üye olmadan gör; randevu için tek adımlık telefon doğrulaması
                yeterli.
              </p>

              <div className="mt-6 flex flex-wrap items-center gap-3 [@media(max-height:720px)]:mt-4">
                <Link href="/randevu" className="btn-light group">
                  Size uygun saati bulalım
                  <ArrowRight size={16} strokeWidth={1.5} aria-hidden className="transition-transform duration-300 group-hover:translate-x-[3px]" />
                </Link>
                <Link href="/#portfolyo" className="btn-outline-light [@media(max-height:720px)]:hidden">
                  İşlerimize bak
                </Link>
              </div>
            </>
          )}

          {/*
            Kahramanın altındaki şerit: puan + bugünün saatleri + adres.
            Puan yalnızca gerçek yorum varsa gösterilir.
          */}
          <dl className="mt-7 flex flex-wrap gap-x-10 gap-y-3 border-t border-white/20 pt-4 text-sm text-white/80 [@media(max-height:720px)]:mt-4 [@media(max-height:720px)]:pt-3">
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
            {/* Alçak ekranlarda gizli: adres "Ziyaret" bölümünde de var. */}
            <div className="[@media(max-height:720px)]:hidden">
              <dt className="text-[11px] uppercase tracking-[0.14em] text-white/60">Adres</dt>
              <dd className="mt-1 font-medium text-white">{branch.address}</dd>
            </div>
          </dl>
        </div>
      </section>

      {/* ================================================================
          2. GÜVEN ŞERİDİ — her rakam veritabanından sayılır
          ============================================================ */}
      <section className="relative border-b border-sand-200 bg-white">
        {/* Fotoğraf ile şeridin birleştiği çizginin ortasında; yalnızca en üstteyken */}
        <ScrollCue targetId="hizmetler" />
        <dl className="bleed grid grid-cols-2 gap-4 py-6 md:grid-cols-4 md:gap-6 md:py-8">
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
                  <span className="display block text-2xl font-light tabular-nums text-plum-700 md:text-4xl">
                    {item.value}
                  </span>
                  <span className="mt-0.5 block text-xs text-ink-500 md:text-sm">{item.label}</span>
                </dd>
              </div>
            ))}
        </dl>
      </section>
      </div>

      {/* ================================================================
          3. KATEGORİLER
          ============================================================ */}
      <section id="hizmetler" className="bleed py-12 md:py-16">
        <p className="eyebrow reveal">Hizmetlerimiz</p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <h2 className="display reveal text-2xl md:text-4xl">Ne yaptırmak istersin?</h2>
          <Link href="/randevu" className="btn-link group">
            Tüm hizmetler ve fiyatlar
            <ArrowRight size={16} strokeWidth={1.5} aria-hidden className="transition-transform duration-300 group-hover:translate-x-[3px]" />
          </Link>
        </div>

        <div className="mt-6 grid grid-cols-2 gap-2.5 md:mt-8 md:grid-cols-4 md:gap-4">
          {categoryCards.map((category) => (
            <Link
              key={category.id}
              href={`/randevu?category=${category.slug}`}
              className="group relative aspect-[4/3] overflow-hidden rounded-[4px] border border-sand-200 md:aspect-[3/4]"
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
                <p className="display text-base leading-tight md:text-xl">
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
          4. VİTRİN HİZMETLERİ — süre ve fiyat açıkça yazılır
          ============================================================ */}
      <section className="bg-white py-12 md:py-16">
        <div className="bleed">
          <p className="eyebrow reveal">Öne çıkanlar</p>
          <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
            <h2 className="display reveal text-2xl md:text-4xl">İmza hizmetlerimiz</h2>
            <p className="muted">Süreler personelin hızına göre değişebilir; fiyatlar sabittir.</p>
          </div>

          <ul className="mt-6 border-t border-sand-200 md:mt-8">
            {featuredServices.map((service) => (
              <li key={service.id} className="border-b border-sand-200">
                <Link
                  href={`/randevu?services=${service.id}`}
                  className="group flex items-start justify-between gap-4 py-4 transition-colors hover:bg-sand-50 md:px-2"
                >
                  <div className="min-w-0">
                    <p className="eyebrow">{service.categoryName}</p>
                    <p className="display mt-1 text-lg md:text-xl">{service.name}</p>
                    {service.description && (
                      <p className="muted mt-1 line-clamp-2 max-w-xl leading-relaxed">
                        {service.description}
                      </p>
                    )}
                    <p className="mt-2 text-xs tabular-nums text-ink-500">
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
        </div>
      </section>

      {/* ================================================================
          5. PORTFOLYO — yapılmış işler; kategori filtresi sayfada çalışır
          ============================================================ */}
      <section id="portfolyo" className="bleed scroll-mt-20 py-12 md:py-16">
        <p className="eyebrow reveal">Portfolyo</p>
        <h2 className="display reveal mt-2 text-2xl md:text-4xl">Son işlerimiz</h2>
        <div className="mt-5">
          {portfolioData.items.length > 0 ? (
            <PortfolioGallery categories={portfolioData.categories} items={portfolioData.items} />
          ) : (
            <p className="muted">Henüz paylaşılmış bir iş yok.</p>
          )}
        </div>
      </section>

      {/* ================================================================
          6. YORUMLAR — sosyal kanıt, tamamı gerçek randevulardan
          ============================================================ */}
      <section id="yorumlar" className="scroll-mt-20 bg-sand-100 py-12 md:py-16">
        <div className="bleed">
          <p className="eyebrow">Değerlendirmeler</p>
          <h2 className="display reveal mt-2 text-2xl md:text-4xl">Müşterilerimiz ne diyor?</h2>
          <p className="muted mt-2 max-w-2xl">
            Tamamı, salonda tamamlanmış randevusu olan müşteriler tarafından yazıldı.
          </p>

          {reviewSummary.count > 0 && reviewSummary.average !== null ? (
            <div className="mt-5 space-y-4">
              {/* Puan özeti — tek satırlık şerit */}
              <div className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-[4px] border border-sand-200 bg-white p-4">
                <div>
                  <div className="flex items-baseline gap-2">
                    <span className="display text-4xl font-light tabular-nums text-plum-700">
                      {reviewSummary.average.toFixed(1).replace('.', ',')}
                    </span>
                    <span className="text-sm text-ink-500">/ 5</span>
                  </div>
                  <Stars value={reviewSummary.average} size="sm" className="mt-1" />
                  <p className="muted mt-1">
                    {reviewSummary.count} değerlendirme · %
                    {Math.round(reviewSummary.positiveRate * 100)} dört yıldız ve üzeri
                  </p>
                </div>

                {/* Yıldız dağılımı — dürüstlük göstergesi */}
                <ul className="min-w-[200px] flex-1 space-y-1">
                  {([5, 4, 3, 2, 1] as const).map((star) => {
                    const value = reviewSummary.distribution[star];
                    const ratio = reviewSummary.count ? (value / reviewSummary.count) * 100 : 0;
                    return (
                      <li key={star} className="flex items-center gap-2 text-xs text-ink-500">
                        <span className="w-3 tabular-nums">{star}</span>
                        <Star size={12} strokeWidth={1.5} aria-hidden className="fill-brass-500 text-brass-500" />
                        <span aria-hidden className="h-1 flex-1 overflow-hidden bg-sand-100">
                          <span className="block h-full bg-plum-600" style={{ width: `${ratio}%` }} />
                        </span>
                        <span className="w-6 text-right tabular-nums">{value}</span>
                      </li>
                    );
                  })}
                </ul>
              </div>

              <ReviewsBrowser reviews={reviews} />
            </div>
          ) : (
            <p className="muted mt-5">Henüz yayınlanmış bir yorum yok.</p>
          )}

          <p className="mt-5 text-center text-sm text-ink-700">
            Sen de değerlendirmek ister misin? Tamamlanan randevularına{' '}
            <Link href="/randevularim" className="btn-link">
              Randevu Sorgula
            </Link>{' '}
            sayfasından puan verebilir, yorumunu yazabilirsin.
          </p>
        </div>
      </section>

      {/* ================================================================
          7. EKİP
          ============================================================ */}
      <section id="ekip" className="bleed scroll-mt-20 py-12 md:py-16">
        <p className="eyebrow reveal">Ekibimiz</p>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <h2 className="display reveal text-2xl md:text-4xl">İşi yapan eller</h2>
          <p className="muted max-w-xl">
            Randevu alırken personelini kendin seçebilirsin. Puanlar yalnızca en az üç yorum almış
            personel için gösterilir.
          </p>
        </div>

        <ul className="mt-6 grid grid-cols-2 gap-3 md:mt-8 md:gap-4 lg:grid-cols-4">
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
                <div className="aspect-[4/3] w-full overflow-hidden bg-sand-100 md:aspect-[4/5]">
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

                <div className="p-3 md:p-4">
                  <p className="display text-base leading-tight md:text-lg">{member.name}</p>
                  <p className="eyebrow mt-1 !text-[10px]">{roleLabel}</p>

                  {rating && (
                    <div className="mt-1.5 flex items-center gap-1.5 text-xs text-ink-500">
                      <Stars value={rating.average} size="sm" />
                      {rating.average.toFixed(1).replace('.', ',')} ({rating.count})
                    </div>
                  )}

                  {specialties.length > 0 && (
                    <p className="muted mt-1.5 leading-relaxed">{specialties.join(' · ')}</p>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      </section>

      {/* ================================================================
          8. KALİTE SÖZÜ — "iyi salon" iddiası değil, çalışma biçimi
          ============================================================ */}
      <section className="bg-white py-12 md:py-16">
        <div className="bleed">
          <p className="eyebrow">Kalite sözümüz</p>
          <h2 className="display reveal mt-2 text-2xl md:text-4xl">
            İyi iş, iyi malzeme ve dürüst bir saat.
          </h2>
          <p className="muted mt-2 max-w-2xl leading-relaxed">
            Bir bakım randevusunun en sinir bozucu tarafı belirsizliktir: ne kadar süreceği, ne
            kadar tutacağı, sıranın ne zaman geleceği. Biz bu üçünü de baştan söylüyoruz.
          </p>

          <ul className="mt-6 grid gap-x-8 gap-y-5 sm:grid-cols-2 md:mt-8">
            {[
              {
                icon: Clock,
                title: 'Randevun dakikası dakikasına planlanır',
                body: 'Birden fazla hizmet seçtiğinde takvimde tek blok açılır; işlemler arka arkaya dizilir.',
              },
              {
                icon: Droplets,
                title: 'Bekleme süren bize yazılır, sana değil',
                body: 'Boya beklemesi gibi pasif süreler personelin takviminde ayrı işaretlenir; kimse kapıda tutulmaz.',
              },
              {
                icon: FlaskConical,
                title: 'Alerji ve hassasiyet kaydın dosyanda durur',
                body: 'Bir kez söylediğin hassasiyet her randevuda personelin ekranında çıkar; gerekirse patch testi hatırlatırız.',
              },
              {
                icon: Sparkles,
                title: 'Tek kullanımlık malzeme, sterilize alet',
                body: 'Törpü gibi malzemeler tek kullanımlıktır; metal aletler her müşteriden sonra sterilize edilir.',
              },
            ].map((item) => (
              <li key={item.title} className="flex gap-3">
                <span
                  aria-hidden
                  className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-brass-300 text-brass-700"
                >
                  <item.icon size={16} strokeWidth={1.5} />
                </span>
                <div>
                  <p className="font-semibold">{item.title}</p>
                  <p className="muted mt-0.5 leading-relaxed">{item.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </section>

      {/* ================================================================
          9. ZİYARET — saatler, adres, telefon
          ============================================================ */}
      <section className="bleed py-12 md:py-16">
        <div className="grid gap-6 md:grid-cols-2 md:items-center md:gap-12">
          <div className="order-2 md:order-1">
            <p className="eyebrow reveal">Bize gel</p>
            <h2 className="display reveal mt-2 text-2xl md:text-4xl">{branch.name}</h2>
            <p className="muted mt-2">{branch.address}</p>

            <dl className="mt-4 divide-y divide-sand-200 border-y border-sand-200">
              {openingHours.map((row) => (
                <div
                  key={row.weekday}
                  className={`flex items-center justify-between py-2 text-sm tabular-nums ${
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

            <div className="mt-5 flex flex-wrap gap-3">
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
            className="order-1 h-44 w-full rounded-[2px] object-cover md:order-2 md:h-80"
          />
        </div>
      </section>

      {/* ================================================================
          10. SIKÇA SORULANLAR
          ============================================================ */}
      <section className="bg-white py-12 md:py-16">
        <div className="bleed max-w-3xl">
          <p className="eyebrow reveal">Sıkça sorulanlar</p>
          <h2 className="display reveal mt-2 text-2xl md:text-4xl">Merak edilenler</h2>

          <div className="mt-6 divide-y divide-sand-200 border-y border-sand-200">
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
                a: 'Boyanın işlem süresi randevuna dahildir ve önceden gösterilir. Bu süre boyunca personelin başka bir kısa işe geçebilir, ama senin saatin kaymaz.',
              },
              {
                q: 'Alerjim var, ne yapmalıyım?',
                a: 'Randevu notuna yazman yeterli; kaydın dosyana işlenir ve her randevuda personelin ekranında görünür. Saç boyası gibi işlemlerde gerekiyorsa 48 saat önceden patch testi öneririz.',
              },
            ].map((item) => (
              <details key={item.q} className="group py-2">
                <summary className="flex cursor-pointer touch-target list-none items-center justify-between gap-4 font-medium">
                  {item.q}
                  <Plus
                    size={18}
                    strokeWidth={1.5}
                    aria-hidden
                    className="shrink-0 text-plum-600 transition-transform duration-300 group-open:rotate-45"
                  />
                </summary>
                <p className="muted mt-2 pb-2 leading-relaxed">{item.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ================================================================
          11. KAPANIŞ ÇAĞRISI
          ============================================================ */}
      <section className="bleed py-12 md:py-16">
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

          <div className="relative px-6 py-10 text-center text-white md:py-14">
            <h2 className="display mx-auto max-w-xl text-2xl font-light leading-tight md:text-4xl">
              Kendinize bir saat ayırmaya hazır mısınız?
            </h2>
            <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-white/85 md:text-base">
              Takvimi açın, size en uygun saati birkaç dokunuşla ayırın.
            </p>
            <Link href="/randevu" className="btn-light group mt-6">
              Saatinizi seçin
              <ArrowRight size={16} strokeWidth={1.5} aria-hidden className="transition-transform duration-300 group-hover:translate-x-[3px]" />
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
