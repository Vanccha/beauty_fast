import Link from 'next/link';

import { adminApi } from '@/lib/admin-api';
import { addDaysToKey, formatDateTr, isDateKey } from '@/lib/time';
import { CalendarBoard, type CalendarAppointment, type CalendarStaff } from './calendar-board';

export const dynamic = 'force-dynamic';

interface CalendarResponse {
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
  const data = await adminApi<CalendarResponse>(`/api/admin/calendar${query}`);
  const date = data.date;

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
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="section-title">{formatDateTr(date)}</h1>
        <div className="flex items-center gap-2">
          <Link href={`/admin/takvim?tarih=${addDaysToKey(date, -1)}`} className="btn-secondary">
            ← Önceki
          </Link>
          <Link href="/admin/takvim" className="btn-secondary">
            Bugün
          </Link>
          <Link href={`/admin/takvim?tarih=${addDaysToKey(date, 1)}`} className="btn-secondary">
            Sonraki →
          </Link>
        </div>
      </div>

      <CalendarBoard
        date={date}
        openMinute={data.openMinute}
        closeMinute={data.closeMinute}
        gridMinutes={data.gridMinutes}
        staff={staff}
        appointments={appointments}
        locks={lockRows}
      />
    </div>
  );
}
