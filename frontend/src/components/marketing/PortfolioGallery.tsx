'use client';

import { useState } from 'react';

import { CategoryIcon } from '@/components/marketing/CategoryIcon';

export interface PortfolioItem {
  id: number;
  title: string;
  imageUrl: string;
  description: string | null;
  category: { id: number; name: string; slug: string } | null;
  staffName: string | null;
}

export interface PortfolioCategory {
  id: number;
  name: string;
  slug: string;
  icon: string | null;
}

/** İlk görünümde gösterilen iş sayısı; kalanı "Daha fazla göster" ile açılır. */
const INITIAL_COUNT = 8;

/**
 * Açılış sayfasındaki portfolyo ızgarası. Kategori filtresi sayfadan
 * ayrılmadan, bellekteki liste üzerinde çalışır (URL değişmez).
 */
export function PortfolioGallery({
  categories,
  items,
}: {
  categories: PortfolioCategory[];
  items: PortfolioItem[];
}) {
  const [active, setActive] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  // Yalnızca en az bir işi olan kategoriler çip olarak gösterilir.
  const usedCategories = categories.filter((c) => items.some((i) => i.category?.slug === c.slug));
  const filtered = active ? items.filter((i) => i.category?.slug === active) : items;
  const visible = expanded ? filtered : filtered.slice(0, INITIAL_COUNT);

  const select = (slug: string | null) => {
    setActive(slug);
    setExpanded(false);
  };

  return (
    <div>
      {usedCategories.length > 0 && (
        <div className="-mx-5 flex gap-2 overflow-x-auto px-5 pb-1 md:mx-0 md:px-0">
          <button
            type="button"
            onClick={() => select(null)}
            aria-pressed={active === null}
            className={`chip shrink-0 ${active === null ? 'chip-active' : ''}`}
          >
            Hepsi
          </button>
          {usedCategories.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => select(c.slug)}
              aria-pressed={active === c.slug}
              className={`chip shrink-0 ${active === c.slug ? 'chip-active' : ''}`}
            >
              <CategoryIcon slug={c.slug} /> {c.name}
            </button>
          ))}
        </div>
      )}

      {filtered.length === 0 ? (
        <p className="muted mt-5">Bu kategoride henüz paylaşılmış iş yok.</p>
      ) : (
        <div className="mt-5 grid grid-cols-2 gap-2.5 md:grid-cols-4 md:gap-3">
          {visible.map((item) => (
            <figure
              key={item.id}
              className="group relative aspect-square overflow-hidden rounded-2xl border border-sand-200 bg-sand-100"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={item.imageUrl}
                alt={item.title}
                loading="lazy"
                className="h-full w-full object-cover transition-transform duration-700 group-hover:scale-[1.03]"
              />
              <figcaption className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-ink-900/85 to-transparent p-2.5 pt-8 text-white">
                <p className="truncate text-xs font-medium">{item.title}</p>
                <p className="truncate text-[11px] text-white/75">
                  {item.category?.name}
                  {item.staffName ? ` · ${item.staffName}` : ''}
                </p>
              </figcaption>
            </figure>
          ))}
        </div>
      )}

      {!expanded && filtered.length > INITIAL_COUNT && (
        <div className="mt-5 text-center">
          <button type="button" onClick={() => setExpanded(true)} className="btn-secondary">
            Daha fazla göster ({filtered.length - INITIAL_COUNT})
          </button>
        </div>
      )}
    </div>
  );
}
