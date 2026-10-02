import { Eye, Flower2, Hand, Scissors, Sparkles, type LucideIcon } from 'lucide-react';

/**
 * Kategori ikonu. Backend'deki `icon` alanı emoji tutar (admin için);
 * müşteri arayüzü emoji yerine slug'a göre çizgi ikon gösterir.
 */
const BY_SLUG: Record<string, LucideIcon> = {
  tirnak: Hand,
  sac: Scissors,
  'kas-kirpik': Eye,
  cilt: Flower2,
};

export function CategoryIcon({ slug, size = 16, className }: { slug: string; size?: number; className?: string }) {
  const Icon = BY_SLUG[slug] ?? Sparkles;
  return <Icon aria-hidden size={size} strokeWidth={1.5} className={className} />;
}
