import { adminApi } from '@/lib/admin-api';
import { formatTl } from '@/lib/api-client';
import { PeriodForm } from './period-form';
import { StaffManager, type StaffRow } from './staff-manager';

export const dynamic = 'force-dynamic';

interface StaffResponse {
  from: string;
  to: string;
  viewerRole: string;
  viewerId: number;
  staff: StaffRow[];
  totals: { count: number; revenue: number; commission: number };
}

interface ServiceOptions {
  categories: { id: number; name: string; services: { id: number; name: string }[] }[];
}

/**
 * Personeller: ekle / düzenle / sil ve dönem bazlı kazanç.
 * Kazanç = TAMAMLANAN randevu cirosu × personelin kazanç yüzdesi.
 */
export default async function StaffPage({
  searchParams,
}: {
  searchParams: Promise<{ from?: string; to?: string }>;
}) {
  const params = await searchParams;
  const query = new URLSearchParams();
  if (params.from) query.set('from', params.from);
  if (params.to) query.set('to', params.to);
  const qs = query.toString() ? `?${query.toString()}` : '';

  const [data, options] = await Promise.all([
    adminApi<StaffResponse>(`/api/admin/staff${qs}`),
    adminApi<ServiceOptions>('/api/admin/service-options'),
  ]);

  return (
    <div className="space-y-4">
      <PeriodForm from={data.from} to={data.to} />

      <div className="grid grid-cols-3 gap-2 md:gap-3">
        <div className="card !p-3">
          <p className="muted text-xs">Tamamlanan randevu</p>
          <p className="display mt-1 text-xl tabular-nums md:text-2xl">{data.totals.count}</p>
        </div>
        <div className="card !p-3">
          <p className="muted text-xs">Toplam ciro</p>
          <p className="display mt-1 text-xl tabular-nums md:text-2xl">{formatTl(data.totals.revenue)}</p>
        </div>
        <div className="card !p-3">
          <p className="muted text-xs">Personel payı</p>
          <p className="display mt-1 text-xl tabular-nums text-plum-700 md:text-2xl">
            {formatTl(data.totals.commission)}
          </p>
        </div>
      </div>

      <StaffManager
        staff={data.staff}
        services={options.categories}
        viewerRole={data.viewerRole}
        viewerId={data.viewerId}
        from={data.from}
        to={data.to}
      />
    </div>
  );
}
