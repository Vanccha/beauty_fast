import { serverApi, type MeResponse } from '@/lib/server-api';
import { BookingFlow } from './booking-flow';

export const dynamic = 'force-dynamic';

interface CatalogResponse {
  categories: { id: number; name: string; slug: string; icon: string | null }[];
  services: {
    id: number;
    categoryId: number | null;
    name: string;
    description: string | null;
    price: number;
    activeBeforeMin: number;
    passiveMin: number;
    activeAfterMin: number;
    bufferMin: number;
    shadowGuestAllowed: boolean;
    shadowHostAllowed: boolean;
  }[];
}

/**
 * Randevu akışının sunucu kabuğu.
 *
 * Katalog SUNUCUDA okunur (ilk boyamada hazır gelir, "yükleniyor"
 * titremesi olmaz); slot taraması ise kullanıcı etkileşimine bağlı
 * olduğu için istemciden `/api/availability` ile yapılır.
 *
 * Veri kaynağı FastAPI backend'idir — bu sayfa veritabanını bilmez.
 */
export default async function BookingPage({
  searchParams,
}: {
  searchParams: Promise<{ services?: string; category?: string; resume?: string }>;
}) {
  const params = await searchParams;

  const [catalog, me] = await Promise.all([
    serverApi<CatalogResponse>('/api/catalog/services'),
    serverApi<MeResponse>('/api/me'),
  ]);

  const { categories, services } = catalog;
  const customer = me.customer;

  const initialServiceIds = (params.services ?? '')
    .split(',')
    .map((s) => Number(s.trim()))
    .filter((n) => Number.isInteger(n) && n > 0 && services.some((s) => s.id === n));

  const initialCategoryId = categories.find((c) => c.slug === params.category)?.id ?? null;

  return (
    <BookingFlow
      categories={categories}
      services={services}
      isMember={Boolean(customer)}
      engagementOptIn={customer?.engagementOptIn ?? true}
      initialServiceIds={initialServiceIds}
      initialCategoryId={initialCategoryId}
      resumeRequested={params.resume === '1'}
    />
  );
}
