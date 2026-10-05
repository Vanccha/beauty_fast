import { ChevronLeft } from 'lucide-react';
import Link from 'next/link';

import { adminApi } from '@/lib/admin-api';
import { RecipeEditor, type RecipeItem, type RecipeService } from './recipe-editor';

export const dynamic = 'force-dynamic';

interface RecipesResponse {
  services: RecipeService[];
  items: RecipeItem[];
}

/**
 * Hizmet reçeteleri: hangi hizmet hangi sarf malzemesini ne kadar kullanır.
 * Randevu "Tamamlandı" olunca stok bu miktarlara göre otomatik düşer.
 */
export default async function RecipesPage() {
  const data = await adminApi<RecipesResponse>('/api/admin/recipes');

  return (
    <div className="space-y-3">
      <Link href="/admin/stok" className="muted inline-flex items-center gap-1 no-underline">
        <ChevronLeft size={14} strokeWidth={1.5} aria-hidden />
        Stok
      </Link>
      <h1 className="display m-0 text-lg font-semibold">Hizmet reçeteleri</h1>
      <p className="muted">
        Reçete, bir hizmetin tek seferde kullandığı malzemeleri belirler; randevu tamamlandığında stok bu
        miktarlara göre otomatik düşer. Yaptığınız değişiklikler yalnızca bundan sonra tamamlanan
        randevuları etkiler; geçmiş stok hareketleri değişmez.
      </p>
      <RecipeEditor services={data.services} items={data.items} />
    </div>
  );
}
