import Link from 'next/link';

import { serverApi } from '@/lib/server-api';

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
    <div className="page-shell space-y-4 pt-6">
      <h1 className="section-title">Portfolyo</h1>

      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
        <Link
          href="/portfolyo"
          className={`btn shrink-0 ${!active ? 'bg-plum-600 text-white' : 'border border-sand-300 bg-white'}`}
        >
          Hepsi
        </Link>
        {categories.map((c) => (
          <Link
            key={c.id}
            href={`/portfolyo?kategori=${c.slug}`}
            className={`btn shrink-0 ${
              active?.id === c.id ? 'bg-plum-600 text-white' : 'border border-sand-300 bg-white'
            }`}
          >
            <span aria-hidden>{c.icon}</span> {c.name}
          </Link>
        ))}
      </div>

      {items.length === 0 ? (
        <p className="muted">Bu kategoride henüz paylaşılmış iş yok.</p>
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          {items.map((item) => (
            <figure
              key={item.id}
              className="overflow-hidden rounded-2xl border border-sand-200 bg-white"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={item.imageUrl}
                alt={item.title}
                loading="lazy"
                className="aspect-square w-full object-cover"
              />
              <figcaption className="p-3">
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
