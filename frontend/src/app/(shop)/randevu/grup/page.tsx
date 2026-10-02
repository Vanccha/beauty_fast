import { serverApi, type MeResponse } from '@/lib/server-api';
import { GroupFlow } from './group-flow';

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
  }[];
}

/**
 * Grup randevusu sunucu kabuğu. Katalog ve oturum sunucuda okunur;
 * `?services=` ilk kişinin başlangıç hizmetleridir.
 */
export default async function GroupBookingPage({
  searchParams,
}: {
  searchParams: Promise<{ services?: string }>;
}) {
  const params = await searchParams;
  const [catalog, me] = await Promise.all([
    serverApi<CatalogResponse>('/api/catalog/services'),
    serverApi<MeResponse>('/api/me'),
  ]);

  const initialServiceIds = (params.services ?? '')
    .split(',')
    .map((s) => Number(s.trim()))
    .filter((n) => Number.isInteger(n) && n > 0 && catalog.services.some((s) => s.id === n));

  return (
    <GroupFlow
      categories={catalog.categories}
      services={catalog.services}
      initialCustomer={me.customer}
      initialServiceIds={initialServiceIds}
    />
  );
}
