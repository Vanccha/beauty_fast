import { ChevronLeft, ChevronRight } from 'lucide-react';
import Link from 'next/link';

import { adminApi } from '@/lib/admin-api';
import { addDaysToKey, formatDateTr, isDateKey } from '@/lib/time';
import { CalendarBoard, type CalendarAppointment, type CalendarStaff } from './calendar-board';
import type { ServiceGroup, Viewer } from './appointment-sheet';
import { DepositListsPanel } from './deposit-lists';
import type { DepositLists, DepositSummary } from '@/lib/deposit';

export const dynamic = 'force-dynamic';

interface CalendarResponse {
  viewer: Viewer;
  depositEnabled: boolean;
  date: string;
  dateLabel: string;
  weekday: number;
  openMinute: number;
  closeMinute: number;
  gridMinutes: number;
  staff: {
    id: number;
    name: string;
    photoUrl: string | null;
    isWorking: boolean;
    startMin: number;
    endMin: number;
    serviceIds: number[];
    timeOff: { startMin: number | null; endMin: number | null; reason: string | null }[];
  }[];
  appointments: {
    id: number;
    staffId: number;
    date: string;
    startMin: number;
    endMin: number;
    status: string;
    version: number;
    totalPrice: number;
    isOpportunity: boolean;
    shadowParentId: number | null;
    source: string;
    createdByStaffId: number | null;
    notes: string | null;
    discountRate: number;
    groupId: string | null;
    deposit: DepositSummary | null;
    customer: { id: number; firstName: string; lastName: string | null; phone: string };
    allergies: { label: string; severity: string }[];
    services: { id: number; name: string }[];
    serviceIds: number[];
    busyIntervals: { start: number; end: number }[];
    passiveIntervals: { start: number; end: number }[];
  }[];
  locks: { id: number; staffId: number; startMin: number; endMin: number; expiresAt: string }[];
}

/**
 * Gün takvimi. Veri sunucuda hazırlanır; sürükle-bırak etkileşimi
 * `CalendarBoard` (istemci) tarafından yürütülür.
 */
export default async function CalendarPage({
  searchParams,
}: {
  searchParams: Promise<{ tarih?: string }>;
}) {
  const params = await searchParams;
  // Geçersiz/eksik tarihte FastAPI bugünü kullanır; dönen tarih esas alınır.
  const query = params.tarih && isDateKey(params.tarih) ? `?date=${params.tarih}` : '';
  const [data, options] = await Promise.all([
    adminApi<CalendarResponse>(`/api/admin/calendar${query}`),
    adminApi<{ categories: ServiceGroup[] }>('/api/admin/service-options'),
  ]);
  const date = data.date;
  // Kapora bekleyen / iade bekleyen listeleri yalnızca yönetici ve sahibe gösterilir.
  const isManager = data.viewer.role === 'OWNER' || data.viewer.role === 'MANAGER';
  const depositLists = isManager ? await adminApi<DepositLists>('/api/admin/deposits') : null;

  const staff: CalendarStaff[] = data.staff.map((s) => ({
    id: s.id,
    name: s.name,
    // Tam gün izin (saat aralığı olmayan kayıt) ustayı o gün kapatır.
    isWorking: s.isWorking && !s.timeOff.some((t) => t.startMin === null),
    startMin: s.startMin,
    endMin: s.endMin,
    serviceIds: s.serviceIds,
    timeOff: s.timeOff,
  }));

  // Meşgul / serbest (pasif) dilimler FastAPI'de hesaplanır.
  const appointments: CalendarAppointment[] = data.appointments.map((a) => ({
    id: a.id,
    staffId: a.staffId,
    startMin: a.startMin,
    endMin: a.endMin,
    status: a.status,
    version: a.version,
    totalPrice: a.totalPrice,
    isOpportunity: a.isOpportunity,
    isShadowChild: a.shadowParentId !== null,
    customerId: a.customer.id,
    customerName: `${a.customer.firstName} ${a.customer.lastName ?? ''}`.trim(),
    customerPhone: a.customer.phone,
    source: a.source,
    notes: a.notes,
    discountRate: a.discountRate,
    deposit: a.deposit,
    groupId: a.groupId,
    serviceNames: a.services.map((x) => x.name),
    serviceIds: a.serviceIds,
    allergyLabels: a.allergies.map((x) => x.label),
    busyIntervals: a.busyIntervals,
    passiveIntervals: a.passiveIntervals,
  }));

  const lockRows = data.locks.map((l) => ({
    id: l.id,
    staffId: l.staffId,
    startMin: l.startMin,
    endMin: l.endMin,
  }));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="eyebrow">{formatDateTr(date)}</p>
        <div className="flex items-center gap-1.5">
          <Link href={`/admin/takvim?tarih=${addDaysToKey(date, -1)}`} className="btn-secondary btn-sm">
            <ChevronLeft size={14} strokeWidth={1.5} aria-hidden /> Önceki
          </Link>
          <Link href="/admin/takvim" className="btn-secondary btn-sm">
            Bugün
          </Link>
          <Link href={`/admin/takvim?tarih=${addDaysToKey(date, 1)}`} className="btn-secondary btn-sm">
            Sonraki <ChevronRight size={14} strokeWidth={1.5} aria-hidden />
          </Link>
        </div>
      </div>

      {depositLists && <DepositListsPanel lists={depositLists} />}

      <CalendarBoard
        date={date}
        depositEnabled={data.depositEnabled}
        openMinute={data.openMinute}
        closeMinute={data.closeMinute}
        gridMinutes={data.gridMinutes}
        staff={staff}
        appointments={appointments}
        locks={lockRows}
        viewer={data.viewer}
        serviceGroups={options.categories}
      />
    </div>
  );
}
