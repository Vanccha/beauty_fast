import Link from 'next/link';

import { serverApi } from '@/lib/server-api';
import { CategoryIcon } from '@/components/marketing/CategoryIcon';

export const dynamic = 'force-dynamic';

interface PortfolioResponse {
  categories: { id: number; name: string; slug: string; icon: string | null }[];
  items: {
    id: number;
    title: string;
    imageUrl: string;
    description: string | null;
    category: { id: number; name: string; slug: string } | null;
    staffName: string | null;
  }[];
}

/**
 * Portfolyo galerisi — herkese açık (üyelik gerekmez).
 *
 * Kategori filtresi URL üzerinden çalışır; böylece istemci JavaScript'i
 * olmadan da gezilebilir ve bağlantı paylaşılabilir.
 */
export default async function PortfolioPage({
  searchParams,
}: {
  searchParams: Promise<{ kategori?: string }>;
}) {
  const { kategori } = await searchParams;

  // Filtre backend'de uygulanır; bağlantı paylaşılabilir kalır.
  const { categories, items } = await serverApi<PortfolioResponse>(
    `/api/portfolio${kategori ? `?category=${encodeURIComponent(kategori)}` : ''}`,
  );

  const active = categories.find((c) => c.slug === kategori) ?? null;

  return (
    <div className="page-shell space-y-8 pb-16 pt-8 md:pt-12">
      <header className="reveal">
        <p className="eyebrow">Galeri</p>
        <h1 className="display mt-2 text-3xl md:text-5xl">Portfolyo</h1>
      </header>

      <div className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1 md:mx-0 md:px-0">
        <Link
          href="/portfolyo"
          className={`chip shrink-0 ${!active ? 'chip-active' : ''}`}
        >
          Hepsi
        </Link>
        {categories.map((c) => (
          <Link
            key={c.id}
            href={`/portfolyo?kategori=${c.slug}`}
            className={`chip shrink-0 ${active?.id === c.id ? 'chip-active' : ''}`}
          >
            <CategoryIcon slug={c.slug} /> {c.name}
          </Link>
        ))}
      </div>

      {items.length === 0 ? (
        <p className="muted">Bu kategoride henüz paylaşılmış iş yok.</p>
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 md:gap-6">
          {items.map((item) => (
            <figure
              key={item.id}
              className="group overflow-hidden rounded-[4px] border border-sand-200 bg-white"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <div className="overflow-hidden">
                <img
                  src={item.imageUrl}
                  alt={item.title}
                  loading="lazy"
                  className="aspect-square w-full object-cover transition-transform duration-700 group-hover:scale-[1.03]"
                />
              </div>
              <figcaption className="p-4">
                <p className="text-sm font-medium">{item.title}</p>
                <p className="muted">
                  {item.category?.name}
                  {item.staffName ? ` · ${item.staffName}` : ''}
                </p>
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </div>
  );
}
