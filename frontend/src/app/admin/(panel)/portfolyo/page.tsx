import { adminApi } from '@/lib/admin-api';
import { PortfolioManager } from './portfolio-manager';

export const dynamic = 'force-dynamic';

interface AdminPortfolioResponse {
  items: {
    id: number;
    title: string;
    imageUrl: string;
    description: string | null;
    isPublished: boolean;
    categoryId: number | null;
    staffId: number | null;
    categoryName: string | null;
    staffName: string | null;
  }[];
  categories: { id: number; name: string }[];
  staff: { id: number; name: string }[];
}

/**
 * Portfolyo yönetimi. Görseller `public/uploads/portfolyo/<yyyy-mm>/`
 * altına yazılır — uzak depolama yoktur.
 */
export default async function AdminPortfolioPage() {
  const { items, categories, staff } = await adminApi<AdminPortfolioResponse>('/api/admin/portfolio');

  return (
    <div className="space-y-3">
      <PortfolioManager
        categories={categories}
        staff={staff}
        items={items.map((i) => ({
          id: i.id,
          title: i.title,
          imageUrl: i.imageUrl,
          description: i.description,
          isPublished: i.isPublished,
          categoryId: i.categoryId,
          staffId: i.staffId,
          categoryName: i.categoryName,
          staffName: i.staffName,
        }))}
      />
    </div>
  );
}
