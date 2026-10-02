'use client';

import { AlertTriangle, X } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useCallback, useRef, useState } from 'react';

import { ApiError, apiSend, formatTl, timeLabel } from '@/lib/api-client';

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
  staff,
  appointments,
  locks,
}: {
  date: string;
  openMinute: number;
  closeMinute: number;
  gridMinutes: number;
  staff: CalendarStaff[];
  appointments: CalendarAppointment[];
  locks: Lock[];
}) {
  const router = useRouter();
  const gridRef = useRef<HTMLDivElement>(null);
  const longPressTimer = useRef<number | null>(null);

  const [drag, setDrag] = useState<DragState | null>(null);
  const [selected, setSelected] = useState<CalendarAppointment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
    if (appointment.status === 'CANCELLED' || appointment.status === 'COMPLETED') return;

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
      setSelected(appointment);
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

  async function changeStatus(appointment: CalendarAppointment, status: string) {
    setBusy(true);
    setError(null);
    try {
      const result = await apiSend<{
        stock: { warnings: string[] } | null;
        loyalty: { points: number; explanation: string } | null;
      }>(`/api/admin/appointments/${appointment.id}/status`, 'PATCH', {
        status,
        expectedVersion: appointment.version,
      });

      const notes: string[] = [];
      if (result.loyalty) notes.push(`Sadakat: ${result.loyalty.explanation}`);
      if (result.stock?.warnings.length) notes.push(...result.stock.warnings);
      if (notes.length) setError(notes.join(' · '));

      setSelected(null);
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

      <p className="muted text-xs">
        Sürükleyerek taşıyın (dokunmatikte basılı tutun). Çizgili alanlar ustanın{' '}
        <strong>serbest</strong> olduğu bekleme süreleridir.
      </p>

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
                <div key={s.id} className="relative flex-1 border-l border-sand-100">
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
                          title={`Usta bu ${iv.end - iv.start} dakikada serbest`}
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
            <div>
              <p className="font-semibold tabular-nums">
                {timeLabel(selected.startMin)}–{timeLabel(selected.endMin)} · {selected.customerName}
              </p>
              <p className="muted">{selected.serviceNames.join(' + ')}</p>
              <p className="mt-1 text-sm font-medium tabular-nums">{formatTl(selected.totalPrice)}</p>
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
              onClick={() => setSelected(null)}
            >
              <X size={16} strokeWidth={1.5} aria-hidden />
            </button>
          </div>

          <div className="flex flex-wrap gap-1.5">
            <a href={`/admin/musteriler/${selected.customerId}`} className="btn-secondary btn-sm">
              CRM kartı
            </a>
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
            <button
              type="button"
              className="btn btn-sm border border-rose-300 bg-white text-rose-700 hover:bg-sand-100"
              disabled={busy || selected.status !== 'CONFIRMED'}
              onClick={() => void changeStatus(selected, 'CANCELLED')}
            >
              İptal
            </button>
          </div>

          <p className="muted text-xs">
            &quot;Tamamlandı&quot; işaretlemek stoktan sarf malzemesini düşer, sadakat puanı yazar ve
            tekrar hatırlatmasını kuyruğa alır. Aynı randevu iki kez tamamlanamaz.
          </p>
        </div>
      )}
    </div>
  );
}
