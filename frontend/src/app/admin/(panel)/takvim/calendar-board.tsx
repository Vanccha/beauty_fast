'use client';

import { AlertTriangle, Plus, X } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useCallback, useRef, useState } from 'react';

import { ApiError, apiSend, formatTl, timeLabel } from '@/lib/api-client';
import {
  appointmentLabel,
  appointmentStatusLabel,
  appointmentTone,
  depositBadge,
  isAwaitingDeposit,
} from '@/lib/appointment-status';
import { refundRemainingLabel, type DepositSummary } from '@/lib/deposit';
import { formatPhone } from '@/lib/phone';
import { AppointmentSheet, type EditTarget, type ServiceGroup, type Viewer } from './appointment-sheet';

/* ------------------------------------------------------------------ */

export interface CalendarStaff {
  id: number;
  name: string;
  isWorking: boolean;
  startMin: number;
  endMin: number;
  serviceIds: number[];
  timeOff: { startMin: number | null; endMin: number | null; reason: string | null }[];
}

export interface CalendarAppointment {
  id: number;
  staffId: number;
  startMin: number;
  endMin: number;
  status: string;
  version: number;
  totalPrice: number;
  isOpportunity: boolean;
  isShadowChild: boolean;
  customerId: number;
  customerName: string;
  customerPhone: string;
  /** "ONLINE" (müşteri) | "ADMIN" (panelden eklendi) */
  source: string;
  notes: string | null;
  discountRate: number;
  /** Kapora özeti (kapora yoksa null) */
  deposit: DepositSummary | null;
  groupId: string | null;
  serviceNames: string[];
  serviceIds: number[];
  allergyLabels: string[];
  busyIntervals: { start: number; end: number }[];
  passiveIntervals: { start: number; end: number }[];
}

interface Lock {
  id: number;
  staffId: number;
  startMin: number;
  endMin: number;
}

/** Dakika başına piksel. 660 dk (09:00–20:00) ≈ 924 px. */
const PPM = 1.4;
/** Dokunmatikte sürüklemeyi başlatan basılı tutma süresi (ms). */
const LONG_PRESS_MS = 220;

interface DragState {
  appointmentId: number;
  version: number;
  durationMin: number;
  /** Karta basıldığı andaki, blok başlangıcına göre dikey ofset (px) */
  grabOffsetPx: number;
  originStaffId: number;
  originStartMin: number;
  targetStaffId: number;
  targetStartMin: number;
  serviceIds: number[];
  moved: boolean;
}

/**
 * ====================================================================
 * SÜRÜKLE-BIRAK TAKVİM
 * ====================================================================
 *
 * Ek kütüphane KULLANILMAZ — Pointer Events yeterlidir ve fare/dokunmatik
 * /kalem girişlerini tek API ile karşılar.
 *
 * Dokunmatik davranışı:
 *  - Kart üzerinde `touch-action: none` (sayfa kaydırması sürüklemeyi
 *    çalmasın diye).
 *  - Parmakla sürükleme ancak ~220 ms basılı tutunca başlar; böylece
 *    listeyi kaydırmak isteyen kullanıcı yanlışlıkla randevu taşımaz.
 *
 * Bırakıldığında `PATCH /api/admin/appointments/[id]/move` çağrılır ve
 * `expectedVersion` gönderilir (optimistic locking). Sunucu reddederse
 * (`VERSION_MISMATCH` veya `SLOT_TAKEN`) kart ESKİ yerine geri döner ve
 * uyarı gösterilir — iyimser güncelleme geri alınır.
 */
export function CalendarBoard({
  date,
  openMinute,
  closeMinute,
  gridMinutes,
  depositEnabled,
  staff,
  appointments,
  locks,
  viewer,
  serviceGroups,
}: {
  date: string;
  depositEnabled: boolean;
  openMinute: number;
  closeMinute: number;
  gridMinutes: number;
  staff: CalendarStaff[];
  appointments: CalendarAppointment[];
  locks: Lock[];
  viewer: Viewer;
  serviceGroups: ServiceGroup[];
}) {
  const router = useRouter();
  const gridRef = useRef<HTMLDivElement>(null);
  const longPressTimer = useRef<number | null>(null);

  const [drag, setDrag] = useState<DragState | null>(null);
  const [selected, setSelected] = useState<CalendarAppointment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [sheet, setSheet] = useState<
    | { mode: 'create'; staffId?: number; startMin?: number }
    | { mode: 'edit'; appointment: CalendarAppointment }
    | null
  >(null);
  /** Detay panelindeki satır içi onay: iptal / geri alma */
  /** Sürükle-bırak sonrası küçük bildirim: "Müşteriye bildir" */
  const [moveToast, setMoveToast] = useState<{ id: number; sent: boolean } | null>(null);
  const [confirming, setConfirming] = useState<'CANCEL' | 'REVERT' | 'PAID' | 'REFUNDED' | null>(null);
  const [notifyCancel, setNotifyCancel] = useState(true);
  /** Kapora: bekleyen randevu iptal nedeni / ödenmiş kaporanın akıbeti / iade mesajı */
  const [cancelReason, setCancelReason] = useState<'DEPOSIT_UNPAID' | 'OTHER'>('DEPOSIT_UNPAID');
  const [forfeit, setForfeit] = useState(false);
  const [notifyRefund, setNotifyRefund] = useState(true);
  const [info, setInfo] = useState<string | null>(null);
  const [revertConflict, setRevertConflict] = useState<string | null>(null);
  const manager = viewer.role === 'OWNER' || viewer.role === 'MANAGER';

  const totalMinutes = closeMinute - openMinute;
  const boardHeight = totalMinutes * PPM;

  const hourMarks: number[] = [];
  for (let m = openMinute; m <= closeMinute; m += 60) hourMarks.push(m);

  /** Ekran koordinatını (personel sütunu, ızgaraya oturmuş dakika) çiftine çevirir. */
  const pointToCell = useCallback(
    (clientX: number, clientY: number, grabOffsetPx: number) => {
      const grid = gridRef.current;
      if (!grid) return null;
      const rect = grid.getBoundingClientRect();

      const columnWidth = rect.width / staff.length;
      const columnIndex = Math.min(
        staff.length - 1,
        Math.max(0, Math.floor((clientX - rect.left) / columnWidth)),
      );

      const rawMinute = openMinute + (clientY - rect.top - grabOffsetPx) / PPM;
      const snapped = Math.round(rawMinute / gridMinutes) * gridMinutes;

      return { staffId: staff[columnIndex].id, startMin: snapped };
    },
    [gridMinutes, openMinute, staff],
  );

  function beginDrag(
    event: React.PointerEvent<HTMLElement>,
    appointment: CalendarAppointment,
  ) {
    if (['CANCELLED', 'COMPLETED', 'NO_SHOW'].includes(appointment.status)) return;

    const target = event.currentTarget;
    const blockRect = target.getBoundingClientRect();
    const grabOffsetPx = event.clientY - blockRect.top;

    const start = () => {
      target.setPointerCapture(event.pointerId);
      setError(null);
      setDrag({
        appointmentId: appointment.id,
        version: appointment.version,
        durationMin: appointment.endMin - appointment.startMin,
        grabOffsetPx,
        originStaffId: appointment.staffId,
        originStartMin: appointment.startMin,
        targetStaffId: appointment.staffId,
        targetStartMin: appointment.startMin,
        serviceIds: appointment.serviceIds,
        moved: false,
      });
    };

    // Fare/kalem: anında. Parmak: basılı tutma gerekir.
    if (event.pointerType === 'touch') {
      longPressTimer.current = window.setTimeout(start, LONG_PRESS_MS);
    } else {
      start();
    }
  }

  function onPointerMove(event: React.PointerEvent<HTMLElement>) {
    if (!drag) return;
    const cell = pointToCell(event.clientX, event.clientY, drag.grabOffsetPx);
    if (!cell) return;

    const clamped = Math.min(
      Math.max(openMinute, cell.startMin),
      closeMinute - drag.durationMin,
    );

    setDrag((prev) =>
      prev
        ? {
            ...prev,
            targetStaffId: cell.staffId,
            targetStartMin: clamped,
            moved:
              prev.moved ||
              cell.staffId !== prev.originStaffId ||
              clamped !== prev.originStartMin,
          }
        : prev,
    );
  }

  function cancelLongPress() {
    if (longPressTimer.current !== null) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  }

  async function endDrag(appointment: CalendarAppointment) {
    cancelLongPress();
    const current = drag;
    setDrag(null);

    // Sürükleme başlamadıysa bu bir tıklamadır → detay panelini aç.
    if (!current || !current.moved) {
      selectAppointment(appointment);
      return;
    }

    // Hedef personel bu hizmetleri yapabiliyor mu? (sunucu da doğrular,
    // burada erken uyarı vermek gereksiz istek atmayı önler)
    const targetStaff = staff.find((s) => s.id === current.targetStaffId);
    if (targetStaff && !current.serviceIds.every((id) => targetStaff.serviceIds.includes(id))) {
      setError(`${targetStaff.name} bu randevudaki hizmetlerin tamamını yapmıyor.`);
      return;
    }

    setBusy(true);
    try {
      await apiSend(`/api/admin/appointments/${current.appointmentId}/move`, 'PATCH', {
        toStaffId: current.targetStaffId,
        toDate: date,
        toStartMin: current.targetStartMin,
        expectedVersion: current.version,
      });
      setMoveToast({ id: current.appointmentId, sent: false });
      router.refresh();
    } catch (e) {
      // Reddedildi → kart eski yerinde kalır (iyimser güncelleme yapılmadı).
      if (e instanceof ApiError && e.code === 'VERSION_MISMATCH') {
        setError('Bu randevu başka bir kullanıcı tarafından güncellendi. Takvim yenileniyor.');
        router.refresh();
      } else if (e instanceof ApiError && e.code === 'SLOT_TAKEN') {
        setError('Hedef saat dolu — randevu eski yerinde bırakıldı.');
      } else {
        setError(e instanceof ApiError ? e.message : 'Taşıma başarısız.');
      }
    } finally {
      setBusy(false);
    }
  }

  function selectAppointment(a: CalendarAppointment | null) {
    setSelected(a);
    setConfirming(null);
    setRevertConflict(null);
    setNotifyCancel(true);
    setCancelReason('DEPOSIT_UNPAID');
    setForfeit(false);
    setNotifyRefund(true);
  }

  async function notifyMoved(id: number) {
    try {
      await apiSend(`/api/admin/appointments/${id}/notify-update`, 'POST');
      setMoveToast({ id, sent: true });
    } catch (e) {
      setMoveToast(null);
      setError(e instanceof ApiError ? e.message : 'Bildirim gönderilemedi.');
    }
  }

  /** Yönetici: Tamamlandı / Gelmedi / İptal durumunu geri alır. */
  async function revertStatus(appointment: CalendarAppointment, force: boolean) {
    setBusy(true);
    setError(null);
    try {
      const result = await apiSend<{ undone?: { depositWarning?: string } }>(
        `/api/admin/appointments/${appointment.id}/revert`,
        'POST',
        {
          expectedVersion: appointment.version,
          force,
        },
      );
      if (result?.undone?.depositWarning) setError(result.undone.depositWarning);
      selectAppointment(null);
      router.refresh();
    } catch (e) {
      if (e instanceof ApiError && e.code === 'SLOT_CONFLICT') {
        setRevertConflict(e.message);
      } else {
        setError(e instanceof ApiError ? e.message : 'Geri alınamadı.');
      }
    } finally {
      setBusy(false);
    }
  }

  /** Yönetici: kapora ulaştı -> randevu onaylanır, müşteriye mesaj gider. */
  async function markDepositPaid(appointment: CalendarAppointment) {
    setBusy(true);
    setError(null);
    try {
      await apiSend(`/api/admin/appointments/${appointment.id}/deposit/paid`, 'POST', {
        expectedVersion: appointment.version,
      });
      selectAppointment(null);
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Kapora işaretlenemedi.');
    } finally {
      setBusy(false);
    }
  }

  async function markDepositRefunded(appointment: CalendarAppointment) {
    setBusy(true);
    setError(null);
    try {
      await apiSend(`/api/admin/appointments/${appointment.id}/deposit/refunded`, 'POST', {
        expectedVersion: appointment.version,
        notifyCustomer: notifyRefund,
      });
      selectAppointment(null);
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'İade işaretlenemedi.');
    } finally {
      setBusy(false);
    }
  }

  async function resendDeposit(appointment: CalendarAppointment) {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      await apiSend(`/api/admin/appointments/${appointment.id}/deposit/resend`, 'POST');
      setInfo('Kapora mesajı müşteriye tekrar gönderilmek üzere kuyruğa alındı.');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Mesaj gönderilemedi.');
    } finally {
      setBusy(false);
    }
  }

  async function changeStatus(
    appointment: CalendarAppointment,
    status: string,
    notify = true,
    extra: { reason?: string; depositForfeit?: boolean } = {},
  ) {
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const result = await apiSend<{
        stock: { warnings: string[] } | null;
        loyalty: { points: number; explanation: string } | null;
      }>(`/api/admin/appointments/${appointment.id}/status`, 'PATCH', {
        status,
        expectedVersion: appointment.version,
        notifyCustomer: notify,
        ...extra,
      });

      const notes: string[] = [];
      if (result.loyalty) notes.push(`Sadakat: ${result.loyalty.explanation}`);
      if (result.stock?.warnings.length) notes.push(...result.stock.warnings);
      if (notes.length) setError(notes.join(' · '));

      selectAppointment(null);
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Durum güncellenemedi.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {error && (
        <p className="rounded-[4px] border border-brass-300 bg-sand-100 px-3 py-2 text-sm text-ink-900">
          {error}
        </p>
      )}

      {info && (
        <p className="rounded-[4px] border border-success-600/30 bg-success-50 px-3 py-2 text-sm text-success-700">
          {info}
        </p>
      )}

      {moveToast && (
        <div className="flex items-center justify-between gap-2 rounded-xl border border-sand-300 bg-white px-3 py-2 text-sm">
          <span>{moveToast.sent ? 'Müşteriye bildirim kuyruğa alındı.' : 'Randevu taşındı.'}</span>
          <span className="flex gap-1.5">
            {!moveToast.sent && (
              <button
                type="button"
                className="btn-secondary btn-sm"
                onClick={() => void notifyMoved(moveToast.id)}
              >
                Müşteriye bildir
              </button>
            )}
            <button
              type="button"
              className="btn-ghost btn-sm"
              aria-label="Kapat"
              onClick={() => setMoveToast(null)}
            >
              <X size={14} strokeWidth={1.5} aria-hidden />
            </button>
          </span>
        </div>
      )}

      <div className="flex items-center justify-between gap-3">
        <p className="muted text-xs">
          Sürükleyerek taşıyın (dokunmatikte basılı tutun); boş bir saate dokunarak randevu ekleyin.
          Çizgili alanlar personelin <strong>serbest</strong> olduğu bekleme süreleridir.
        </p>
        <button
          type="button"
          className="btn-primary btn-sm shrink-0"
          onClick={() => setSheet({ mode: 'create' })}
        >
          <Plus size={14} strokeWidth={1.5} aria-hidden /> Randevu ekle
        </button>
      </div>

      <div className="overflow-x-auto rounded-[4px] border border-sand-200 bg-white">
        <div className="flex min-w-[640px]">
          {/* Saat ekseni */}
          <div className="w-14 shrink-0 border-r border-sand-200">
            <div className="h-12 border-b border-sand-200" />
            <div className="relative" style={{ height: boardHeight }}>
              {hourMarks.map((m) => (
                <div
                  key={m}
                  className="absolute left-0 right-0 -translate-y-1/2 pr-1 text-right text-[11px] tabular-nums text-ink-500"
                  style={{ top: (m - openMinute) * PPM }}
                >
                  {timeLabel(m)}
                </div>
              ))}
            </div>
          </div>

          {/* Personel sütunları */}
          <div className="flex-1">
            <div className="flex h-12 border-b border-sand-200">
              {staff.map((s) => (
                <div
                  key={s.id}
                  className="flex flex-1 flex-col items-center justify-center border-l border-sand-100 px-1"
                >
                  <span className="truncate text-xs font-semibold uppercase tracking-wide text-ink-900">{s.name}</span>
                  {!s.isWorking && <span className="text-[10px] text-ink-500">izinli</span>}
                </div>
              ))}
            </div>

            <div
              ref={gridRef}
              className="drag-surface relative flex"
              style={{ height: boardHeight }}
              onPointerMove={onPointerMove}
            >
              {/* Saat çizgileri */}
              {hourMarks.map((m) => (
                <div
                  key={m}
                  className="pointer-events-none absolute left-0 right-0 border-t border-sand-100"
                  style={{ top: (m - openMinute) * PPM }}
                />
              ))}

              {staff.map((s) => (
                <div
                  key={s.id}
                  className="relative flex-1 border-l border-sand-100"
                  onClick={(e) => {
                    // Randevu kartına / detay tıklamalarına karışma.
                    if ((e.target as HTMLElement).closest('article') || drag) return;
                    const rect = e.currentTarget.getBoundingClientRect();
                    const raw = openMinute + (e.clientY - rect.top) / PPM;
                    const snapped = Math.max(
                      openMinute,
                      Math.floor(raw / gridMinutes) * gridMinutes,
                    );
                    setSheet({ mode: 'create', staffId: s.id, startMin: snapped });
                  }}
                >
                  {/* Mesai dışı / izin gölgesi */}
                  {!s.isWorking && <div className="absolute inset-0 bg-sand-100/70" />}
                  {s.isWorking && s.startMin > openMinute && (
                    <div
                      className="absolute left-0 right-0 bg-sand-100/70"
                      style={{ top: 0, height: (s.startMin - openMinute) * PPM }}
                    />
                  )}
                  {s.isWorking && s.endMin < closeMinute && (
                    <div
                      className="absolute left-0 right-0 bg-sand-100/70"
                      style={{
                        top: (s.endMin - openMinute) * PPM,
                        height: (closeMinute - s.endMin) * PPM,
                      }}
                    />
                  )}

                  {/* Geçici rezervasyonlar (başka bir kullanıcı slotu tutuyor) */}
                  {locks
                    .filter((l) => l.staffId === s.id)
                    .map((l) => (
                      <div
                        key={`lock-${l.id}`}
                        className="absolute left-1 right-1 rounded-[2px] border border-dashed border-brass-500 bg-sand-100/80 px-1 py-0.5 text-[10px] text-brass-700"
                        style={{
                          top: (l.startMin - openMinute) * PPM,
                          height: (l.endMin - l.startMin) * PPM,
                        }}
                      >
                        Tutuluyor
                      </div>
                    ))}

                  {/* Randevular */}
                  {appointments
                    .filter((a) =>
                      drag?.appointmentId === a.id
                        ? drag.targetStaffId === s.id
                        : a.staffId === s.id,
                    )
                    .map((a) => {
                      const isDragging = drag?.appointmentId === a.id;
                      const startMin = isDragging ? drag.targetStartMin : a.startMin;
                      const duration = a.endMin - a.startMin;
                      const cancelled = a.status === 'CANCELLED' || a.status === 'NO_SHOW';
                      const pending = a.status === 'PENDING';
                      const awaiting = isAwaitingDeposit(a.status, a.deposit?.status);

                      return (
                        <article
                          key={a.id}
                          onPointerDown={(e) => beginDrag(e, a)}
                          onPointerUp={() => void endDrag(a)}
                          onPointerCancel={cancelLongPress}
                          className={`drag-surface absolute left-1 right-1 overflow-hidden rounded-[3px] border text-[11px] ${
                            isDragging ? 'dragging z-20' : 'z-10'
                          } ${
                            cancelled
                              ? 'border-sand-300 bg-sand-100 text-ink-500 line-through'
                              : a.isShadowChild
                                ? 'border-plum-400 bg-plum-100'
                                : awaiting
                                  ? `border-dashed bg-brass-300/20 ${a.deposit?.overdue ? 'border-danger-600' : 'border-brass-500'}`
                                  : pending
                                    ? 'border-dashed border-plum-300 bg-white'
                                    : 'border-plum-300 bg-white'
                          }`}
                          style={{
                            top: (startMin - openMinute) * PPM,
                            height: Math.max(28, duration * PPM),
                            cursor: cancelled ? 'default' : 'grab',
                          }}
                        >
                          {/* Meşgul / serbest dilim şeritleri */}
                          {!cancelled && (
                            <div className="pointer-events-none absolute inset-y-0 left-0 w-1.5">
                              {a.busyIntervals.map((iv) => (
                                <div
                                  key={`b-${iv.start}`}
                                  className="absolute left-0 w-1.5 bg-plum-500"
                                  style={{
                                    top: (iv.start - a.startMin) * PPM,
                                    height: (iv.end - iv.start) * PPM,
                                  }}
                                />
                              ))}
                              {a.passiveIntervals.map((iv) => (
                                <div
                                  key={`p-${iv.start}`}
                                  className="shadow-window absolute left-0 w-1.5"
                                  style={{
                                    top: (iv.start - a.startMin) * PPM,
                                    height: (iv.end - iv.start) * PPM,
                                  }}
                                />
                              ))}
                            </div>
                          )}

                          <div className="px-2 py-1 pl-3">
                            <p className="truncate font-semibold tabular-nums">
                              {timeLabel(startMin)} {a.customerName}
                            </p>
                            <p className="truncate text-ink-500">{a.serviceNames.join(' + ')}</p>
                            {awaiting && (
                              <p
                                className={`truncate font-semibold ${a.deposit?.overdue ? 'text-danger-700' : 'text-brass-700'}`}
                              >
                                Kapora bekleniyor
                                {a.deposit?.amount ? ` · ${formatTl(a.deposit.amount)}` : ''}
                              </p>
                            )}
                            {a.allergyLabels.length > 0 && (
                              <p className="flex items-center gap-1 truncate font-semibold text-rose-700">
                                <AlertTriangle size={12} strokeWidth={1.5} className="shrink-0" aria-hidden />
                                <span className="truncate">{a.allergyLabels.join(', ')}</span>
                              </p>
                            )}
                          </div>
                        </article>
                      );
                    })}

                  {/* Pasif (gölge) pencerelerin sütun genelinde görsel izi */}
                  {appointments
                    .filter((a) => a.staffId === s.id && drag?.appointmentId !== a.id)
                    .flatMap((a) =>
                      a.passiveIntervals.map((iv) => (
                        <div
                          key={`sw-${a.id}-${iv.start}`}
                          className="shadow-window pointer-events-none absolute left-1 right-1 z-0 rounded-[2px]"
                          style={{
                            top: (iv.start - openMinute) * PPM,
                            height: (iv.end - iv.start) * PPM,
                          }}
                          title={`Personel bu ${iv.end - iv.start} dakikada serbest`}
                        />
                      )),
                    )}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* ---------------- Detay paneli ---------------- */}
      {selected && (
        <div className="card space-y-3 !p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-1.5">
                <p className="font-semibold tabular-nums">
                  {timeLabel(selected.startMin)}–{timeLabel(selected.endMin)} · {selected.customerName}
                </p>
                <span
                  className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${appointmentTone(selected.status, selected.deposit?.status)}`}
                >
                  {appointmentLabel(selected.status, selected.deposit?.status)}
                </span>
                {(() => {
                  const badge = depositBadge(selected.deposit?.status);
                  return badge ? (
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${badge.tone}`}>
                      {badge.label}
                    </span>
                  ) : null;
                })()}
                {selected.source === 'ADMIN' && (
                  <span className="rounded-full bg-sand-100 px-2 py-0.5 text-[11px] font-semibold text-ink-700">
                    Panelden eklendi
                  </span>
                )}
              </div>
              <p className="muted">{selected.serviceNames.join(' + ')}</p>
              <p className="muted text-xs tabular-nums">{formatPhone(selected.customerPhone)}</p>
              <p className="mt-1 text-sm font-medium tabular-nums">
                {formatTl(selected.totalPrice)}
                {selected.discountRate > 0 && (
                  <span className="ml-1.5 text-xs font-normal text-success-700">
                    %{Math.round(selected.discountRate * 100)} indirimli
                  </span>
                )}
              </p>
              {selected.deposit && selected.deposit.amount ? (
                <p
                  className={`mt-1 text-sm tabular-nums ${selected.deposit.overdue ? 'font-semibold text-danger-700' : 'text-ink-700'}`}
                >
                  Kapora: {formatTl(selected.deposit.amount)}
                  {selected.deposit.status === 'AWAITING' && selected.deposit.overdue && ' · süre geçti'}
                  {selected.deposit.status === 'PAID' &&
                    selected.deposit.paidAt &&
                    ` · ${new Date(selected.deposit.paidAt).toLocaleString('tr-TR', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })} tarihinde ödendi`}
                  {selected.deposit.status === 'REFUND_DUE' &&
                    selected.deposit.refundDueAt &&
                    ` · iade süresi: ${refundRemainingLabel(Math.round((new Date(selected.deposit.refundDueAt).getTime() - Date.now()) / 60000))}`}
                </p>
              ) : null}
              {selected.notes && <p className="mt-1 text-sm text-ink-700">Not: {selected.notes}</p>}
              {selected.allergyLabels.length > 0 && (
                <p className="mt-2 flex items-center gap-1.5 rounded-[2px] border border-rose-300 px-2 py-1 text-sm font-medium text-rose-700">
                  <AlertTriangle size={14} strokeWidth={1.5} className="shrink-0" aria-hidden />
                  Alerji: {selected.allergyLabels.join(', ')}
                </p>
              )}
            </div>
            <button
              type="button"
              className="btn-ghost btn-sm"
              aria-label="Kapat"
              onClick={() => selectAppointment(null)}
            >
              <X size={16} strokeWidth={1.5} aria-hidden />
            </button>
          </div>

          {(() => {
            const active = selected.status === 'PENDING' || selected.status === 'CONFIRMED';
            const final = ['COMPLETED', 'NO_SHOW', 'CANCELLED'].includes(selected.status);
            const awaiting = isAwaitingDeposit(selected.status, selected.deposit?.status);
            const paidActive = selected.deposit?.status === 'PAID' && selected.status === 'CONFIRMED';
            const refundDue = selected.deposit?.status === 'REFUND_DUE';
            return (
              <>
                <div className="flex flex-wrap gap-1.5">
                  <a href={`/admin/musteriler/${selected.customerId}`} className="btn-secondary btn-sm">
                    CRM kartı
                  </a>
                  {active && (
                    <button
                      type="button"
                      className="btn-secondary btn-sm"
                      disabled={busy}
                      onClick={() => setSheet({ mode: 'edit', appointment: selected })}
                    >
                      Düzenle
                    </button>
                  )}
                  {awaiting && manager && (
                    <>
                      <button
                        type="button"
                        className="btn-primary btn-sm"
                        disabled={busy}
                        onClick={() => setConfirming(confirming === 'PAID' ? null : 'PAID')}
                      >
                        Kapora ödendi
                      </button>
                      <button
                        type="button"
                        className="btn-secondary btn-sm"
                        disabled={busy}
                        onClick={() => void resendDeposit(selected)}
                      >
                        Kapora mesajını tekrar gönder
                      </button>
                    </>
                  )}
                  {refundDue && manager && (
                    <button
                      type="button"
                      className="btn-primary btn-sm"
                      disabled={busy}
                      onClick={() => setConfirming(confirming === 'REFUNDED' ? null : 'REFUNDED')}
                    >
                      Kapora iade edildi
                    </button>
                  )}
                  {selected.status === 'PENDING' && !awaiting && (
                    <button
                      type="button"
                      className="btn-primary btn-sm"
                      disabled={busy}
                      onClick={() => void changeStatus(selected, 'CONFIRMED')}
                    >
                      Onayla
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-sm border border-emerald-300 bg-white text-emerald-700 hover:bg-sand-100"
                    disabled={busy || selected.status !== 'CONFIRMED'}
                    onClick={() => void changeStatus(selected, 'COMPLETED')}
                  >
                    Tamamlandı
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm border border-brass-300 bg-white text-brass-700 hover:bg-sand-100"
                    disabled={busy || selected.status !== 'CONFIRMED'}
                    onClick={() => void changeStatus(selected, 'NO_SHOW')}
                  >
                    Gelmedi
                  </button>
                  {active && (
                    <button
                      type="button"
                      className="btn btn-sm border border-rose-300 bg-white text-rose-700 hover:bg-sand-100"
                      disabled={busy}
                      onClick={() => setConfirming(confirming === 'CANCEL' ? null : 'CANCEL')}
                    >
                      İptal
                    </button>
                  )}
                  {final && manager && (
                    <button
                      type="button"
                      className="btn-secondary btn-sm"
                      disabled={busy}
                      onClick={() => {
                        setRevertConflict(null);
                        setConfirming(confirming === 'REVERT' ? null : 'REVERT');
                      }}
                    >
                      Geri al
                    </button>
                  )}
                </div>

                {awaiting && !manager && (
                  <p className="muted rounded-xl bg-sand-100 px-3 py-2 text-xs">
                    Kapora bekleniyor. “Kapora ödendi” işaretini yalnızca yönetici veya salon sahibi yapabilir.
                  </p>
                )}

                {confirming === 'PAID' && awaiting && manager && (
                  <div className="space-y-2 rounded-xl border border-sand-300 bg-white px-3 py-2.5">
                    <p className="text-sm">
                      {formatTl(selected.deposit?.amount ?? 0)} kapora hesabınıza ulaştı mı? Randevu “Onaylandı” olur ve
                      müşteriye “kaporanız ulaştı” mesajı gider.
                      {selected.groupId && ' Grup randevusunda gruptaki tüm kapora bekleyen randevular birlikte onaylanır.'}
                    </p>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="btn-primary btn-sm"
                        disabled={busy}
                        onClick={() => void markDepositPaid(selected)}
                      >
                        Evet, ulaştı
                      </button>
                      <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirming(null)}>
                        Vazgeç
                      </button>
                    </div>
                  </div>
                )}

                {confirming === 'REFUNDED' && refundDue && manager && (
                  <div className="space-y-2 rounded-xl border border-sand-300 bg-white px-3 py-2.5">
                    <p className="text-sm">{formatTl(selected.deposit?.amount ?? 0)} müşteriye iade edildi olarak işaretlensin mi?</p>
                    <label className="flex items-center gap-2 text-sm">
                      <input type="checkbox" checked={notifyRefund} onChange={(e) => setNotifyRefund(e.target.checked)} />
                      Müşteriye “Kaporanız iade edilmiştir” mesajı gönder
                    </label>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="btn-primary btn-sm"
                        disabled={busy}
                        onClick={() => void markDepositRefunded(selected)}
                      >
                        Evet, iade edildi
                      </button>
                      <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirming(null)}>
                        Vazgeç
                      </button>
                    </div>
                  </div>
                )}

                {confirming === 'CANCEL' && active && (
                  <div className="space-y-2 rounded-xl border border-rose-300 bg-white px-3 py-2.5">
                    <p className="text-sm">Bu randevuyu iptal etmek istediğinize emin misiniz?</p>
                    {awaiting && (
                      <fieldset className="space-y-1 text-sm">
                        <legend className="label">İptal nedeni</legend>
                        <label className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="cancel-reason"
                            checked={cancelReason === 'DEPOSIT_UNPAID'}
                            onChange={() => setCancelReason('DEPOSIT_UNPAID')}
                          />
                          Kapora yatırılmadı
                        </label>
                        <label className="flex items-center gap-2">
                          <input
                            type="radio"
                            name="cancel-reason"
                            checked={cancelReason === 'OTHER'}
                            onChange={() => setCancelReason('OTHER')}
                          />
                          Diğer
                        </label>
                      </fieldset>
                    )}
                    {paidActive && (
                      <fieldset className="space-y-1 text-sm">
                        <legend className="label">Ödenmiş kapora ({formatTl(selected.deposit?.amount ?? 0)})</legend>
                        <label className="flex items-center gap-2">
                          <input type="radio" name="cancel-forfeit" checked={!forfeit} onChange={() => setForfeit(false)} />
                          İade edilecek (48 saat içinde)
                        </label>
                        {manager && (
                          <label className="flex items-center gap-2">
                            <input type="radio" name="cancel-forfeit" checked={forfeit} onChange={() => setForfeit(true)} />
                            Kapora yanar (iade edilmez)
                          </label>
                        )}
                      </fieldset>
                    )}
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={notifyCancel}
                        onChange={(e) => setNotifyCancel(e.target.checked)}
                      />
                      Müşteriye iptal mesajı gönder
                    </label>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="btn-danger btn-sm"
                        disabled={busy}
                        onClick={() =>
                          void changeStatus(selected, 'CANCELLED', notifyCancel, {
                            reason: awaiting && cancelReason === 'DEPOSIT_UNPAID' ? 'DEPOSIT_UNPAID' : undefined,
                            depositForfeit: paidActive && forfeit ? true : undefined,
                          })
                        }
                      >
                        Evet, iptal et
                      </button>
                      <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirming(null)}>
                        Vazgeç
                      </button>
                    </div>
                  </div>
                )}

                {confirming === 'REVERT' && final && manager && (
                  <div className="space-y-2 rounded-xl border border-sand-300 bg-white px-3 py-2.5">
                    <p className="text-sm">
                      &quot;{appointmentStatusLabel(selected.status)}&quot; işareti geri alınıp randevu
                      &quot;Onaylandı&quot; durumuna dönecek.
                      {selected.status === 'COMPLETED' &&
                        ' Sadakat puanı ve stok düşümü de geri alınır, bekleyen ziyaret sonrası mesajı iptal edilir.'}
                      {selected.status === 'NO_SHOW' && ' Gelmedi kaydı risk havuzundan silinir.'}
                      {selected.status === 'CANCELLED' && ' Saat hâlâ boşsa yeniden dolar.'}
                      {selected.deposit?.status === 'REFUND_DUE' && ' Kapora tekrar “ödendi” durumuna döner.'}
                      {selected.deposit?.status === 'FORFEITED' && ' Kapora tekrar “ödendi” durumuna döner.'}
                      {selected.deposit?.status === 'REFUNDED' &&
                        ' Kapora zaten iade edildi; geri alma sonrası kapora “iade edildi” kalır, gerekirse yeniden tahsil edin.'}
                      {selected.status === 'CANCELLED' && selected.deposit?.status === 'NONE' && selected.deposit.amount && ' Kapora yeniden beklenir.'}
                    </p>
                    {revertConflict && (
                      <p className="rounded-lg bg-sand-100 px-2 py-1.5 text-sm text-brass-700">
                        {revertConflict}
                      </p>
                    )}
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="btn-primary btn-sm"
                        disabled={busy}
                        onClick={() => void revertStatus(selected, Boolean(revertConflict))}
                      >
                        {revertConflict ? 'Yine de geri al' : 'Evet, geri al'}
                      </button>
                      <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirming(null)}>
                        Vazgeç
                      </button>
                    </div>
                  </div>
                )}
              </>
            );
          })()}

          <p className="muted text-xs">
            &quot;Tamamlandı&quot; işaretlemek stoktan sarf malzemesini düşer, sadakat puanı yazar ve
            tekrar hatırlatmasını kuyruğa alır. Aynı randevu iki kez tamamlanamaz; yanlış işaretlenirse
            yönetici &quot;Geri al&quot; yapabilir.
          </p>
        </div>
      )}

      {/* ---------------- Randevu ekle / düzenle ---------------- */}
      {sheet && (
        <AppointmentSheet
          key={sheet.mode === 'edit' ? `e-${sheet.appointment.id}-${sheet.appointment.version}` : 'create'}
          mode={sheet.mode}
          date={date}
          staff={staff.map((st) => ({ id: st.id, name: st.name, serviceIds: st.serviceIds }))}
          groups={serviceGroups}
          viewer={viewer}
          openMinute={openMinute}
          closeMinute={closeMinute}
          gridMinutes={gridMinutes}
          depositEnabled={depositEnabled}
          initial={sheet.mode === 'create' ? { staffId: sheet.staffId, startMin: sheet.startMin } : undefined}
          appointment={sheet.mode === 'edit' ? toEditTarget(sheet.appointment) : undefined}
          onClose={() => setSheet(null)}
          onSaved={() => {
            setSheet(null);
            selectAppointment(null);
            router.refresh();
          }}
        />
      )}

      {/* Mobilde her an erişilebilir */}
      <button
        type="button"
        aria-label="Randevu ekle"
        className="btn-primary fixed bottom-5 right-4 z-30 shadow-lg md:hidden"
        onClick={() => setSheet({ mode: 'create' })}
      >
        <Plus size={16} strokeWidth={1.5} aria-hidden /> Randevu ekle
      </button>
    </div>
  );
}

function toEditTarget(a: CalendarAppointment): EditTarget {
  return {
    id: a.id,
    version: a.version,
    status: a.status,
    staffId: a.staffId,
    startMin: a.startMin,
    serviceIds: a.serviceIds,
    customerId: a.customerId,
    customerName: a.customerName,
    customerPhone: a.customerPhone,
    notes: a.notes,
    totalPrice: a.totalPrice,
    depositStatus: a.deposit?.status,
  };
}
