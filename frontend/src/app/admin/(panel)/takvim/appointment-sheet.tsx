'use client';

import { AlertTriangle, Search, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { PhoneInput } from '@/components/auth/PhoneInput';
import { ApiError, apiGet, apiSend, durationLabel, formatTl, timeLabel } from '@/lib/api-client';
import { formatPhone, isValidMobile, normalizePhone } from '@/lib/phone';

/* ------------------------------------------------------------------ */

export interface SheetStaff {
  id: number;
  name: string;
  serviceIds: number[];
}

export interface ServiceGroup {
  id: number;
  name: string;
  services: { id: number; name: string; price: number; durationMin: number }[];
}

export interface Viewer {
  id: number;
  role: string;
}

/** Düzenlenen randevunun formda ihtiyaç duyduğu alanlar. */
export interface EditTarget {
  id: number;
  version: number;
  status: string;
  staffId: number;
  startMin: number;
  serviceIds: number[];
  customerId: number;
  customerName: string;
  customerPhone: string;
  notes: string | null;
  totalPrice: number;
  /** Kapora durumu (NONE | AWAITING | PAID | ...) */
  depositStatus?: string;
}

interface Conflict {
  kind: string;
  message: string;
}

interface Preview {
  totalMin: number;
  endLabel: string;
  basePrice: number;
  discountRate: number;
  price: number;
  conflicts: Conflict[];
  canForce: boolean;
}

interface FoundCustomer {
  id: number;
  firstName: string;
  lastName: string | null;
  phone: string;
}

type CustomerChoice =
  | { kind: 'existing'; id: number; label: string; phone: string }
  | { kind: 'new' }
  | null;

const isManager = (v: Viewer) => v.role === 'OWNER' || v.role === 'MANAGER';

/**
 * Randevu ekle / düzenle paneli (mobilde alttan açılan sayfa).
 *
 * Süre, fiyat ve çakışma sunucuda hesaplanır (`/appointments/preview`);
 * burada yalnızca gösterilir. Çakışmada yönetici "Yine de ekle" ile
 * (satır içi onayla) `force` gönderebilir.
 */
export function AppointmentSheet({
  mode,
  date: initialDate,
  staff,
  groups,
  viewer,
  openMinute,
  closeMinute,
  gridMinutes,
  depositEnabled,
  initial,
  appointment,
  onClose,
  onSaved,
}: {
  mode: 'create' | 'edit';
  date: string;
  staff: SheetStaff[];
  groups: ServiceGroup[];
  viewer: Viewer;
  openMinute: number;
  closeMinute: number;
  gridMinutes: number;
  /** Salon kaporayı açtıysa "Kapora iste" kutusu gösterilir. */
  depositEnabled: boolean;
  initial?: { staffId?: number; startMin?: number };
  appointment?: EditTarget;
  onClose: () => void;
  onSaved: () => void;
}) {
  const edit = mode === 'edit' && appointment;
  const manager = isManager(viewer);

  const [customer, setCustomer] = useState<CustomerChoice>(
    edit
      ? {
          kind: 'existing',
          id: appointment.customerId,
          label: appointment.customerName,
          phone: appointment.customerPhone,
        }
      : null,
  );
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<FoundCustomer[]>([]);
  const [newFirst, setNewFirst] = useState('');
  const [newLast, setNewLast] = useState('');
  const [newPhone, setNewPhone] = useState('');

  const defaultStaff =
    edit
      ? appointment.staffId
      : (initial?.staffId ?? (manager ? staff[0]?.id : viewer.id) ?? staff[0]?.id ?? 0);
  const [staffId, setStaffId] = useState<number>(defaultStaff);
  const [date, setDate] = useState(initialDate);
  const [startMin, setStartMin] = useState<number>(
    edit ? appointment.startMin : (initial?.startMin ?? openMinute),
  );
  const [serviceIds, setServiceIds] = useState<number[]>(edit ? appointment.serviceIds : []);
  const [status, setStatus] = useState<'CONFIRMED' | 'PENDING'>('CONFIRMED');
  const [applyDiscount, setApplyDiscount] = useState(true);
  const [priceText, setPriceText] = useState('');
  const [notes, setNotes] = useState(edit ? (appointment.notes ?? '') : '');
  const [notify, setNotify] = useState(!edit);
  const [requestDeposit, setRequestDeposit] = useState(false);

  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [serverConflicts, setServerConflicts] = useState<Conflict[] | null>(null);
  const [confirmForce, setConfirmForce] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const currentStaff = staff.find((s) => s.id === staffId);
  const serviceById = useMemo(() => {
    const map = new Map<number, ServiceGroup['services'][number]>();
    groups.forEach((g) => g.services.forEach((s) => map.set(s.id, s)));
    return map;
  }, [groups]);

  const timeOptions = useMemo(() => {
    const list: number[] = [];
    for (let m = openMinute; m < closeMinute; m += gridMinutes) list.push(m);
    if (!list.includes(startMin)) list.push(startMin);
    return list.sort((a, b) => a - b);
  }, [openMinute, closeMinute, gridMinutes, startMin]);

  /* ---------- müşteri arama ---------- */
  const searchSeq = useRef(0);
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setFound([]);
      return;
    }
    const seq = ++searchSeq.current;
    const t = window.setTimeout(() => {
      apiGet<{ customers: FoundCustomer[] }>(
        `/api/admin/customers/search?q=${encodeURIComponent(q)}`,
      )
        .then((r) => {
          if (seq === searchSeq.current) setFound(r.customers);
        })
        .catch(() => undefined);
    }, 250);
    return () => window.clearTimeout(t);
  }, [query]);

  /* ---------- süre / fiyat / çakışma önizlemesi ---------- */
  const customerIdForPreview = customer?.kind === 'existing' ? customer.id : undefined;
  const serviceKey = serviceIds.join(',');
  useEffect(() => {
    if (serviceIds.length === 0 || !staffId || !date) {
      setPreview(null);
      setPreviewError(null);
      return;
    }
    let cancelled = false;
    const t = window.setTimeout(() => {
      apiSend<Preview>('/api/admin/appointments/preview', 'POST', {
        serviceIds,
        staffId,
        date,
        startMin,
        applyDiscount,
        customerId: customerIdForPreview,
        excludeAppointmentId: edit ? appointment.id : undefined,
      })
        .then((p) => {
          if (cancelled) return;
          setPreview(p);
          setPreviewError(null);
        })
        .catch((e) => {
          if (cancelled) return;
          setPreview(null);
          setPreviewError(e instanceof ApiError ? e.message : 'Önizleme alınamadı.');
        });
    }, 300);
    return () => {
      cancelled = true;
      window.clearTimeout(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serviceKey, staffId, date, startMin, applyDiscount, customerIdForPreview]);

  // Girdi değişince eski sunucu çakışması ve onay sıfırlanır.
  useEffect(() => {
    setServerConflicts(null);
    setConfirmForce(false);
  }, [serviceKey, staffId, date, startMin, customerIdForPreview]);

  const conflicts: Conflict[] = serverConflicts ?? preview?.conflicts ?? [];
  const hasConflict = conflicts.length > 0;

  function toggleService(id: number) {
    setServiceIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  }

  function buildCustomerPart(): Record<string, unknown> | string {
    if (!customer) return 'Müşteri seçin ya da yeni müşteri ekleyin.';
    if (customer.kind === 'existing') return { customerId: customer.id };
    const first = newFirst.trim();
    if (!first) return 'Yeni müşteri için ad girin.';
    const phone = normalizePhone(newPhone);
    if (!isValidMobile(phone)) {
      return 'Geçerli bir cep telefonu girin (telefonsuz kayıt yapılamaz; yurtdışı için ülke kodunu seçin).';
    }
    return {
      newCustomer: { firstName: first, lastName: newLast.trim() || undefined, phone },
    };
  }

  async function submit(force: boolean) {
    setError(null);
    if (serviceIds.length === 0) return setError('En az bir hizmet seçin.');
    const price = priceText.trim() === '' ? null : Number(priceText.replace(',', '.'));
    if (price !== null && (!Number.isFinite(price) || price < 0)) {
      return setError('Fiyat geçerli bir sayı olmalı.');
    }

    setBusy(true);
    try {
      if (edit) {
        const body: Record<string, unknown> = {
          expectedVersion: appointment.version,
          serviceIds,
          staffId,
          date,
          startMin,
          notes: notes.trim(),
          applyDiscount,
          notifyCustomer: notify,
          force,
        };
        if (price !== null) body.priceOverride = price;
        const customerChanged =
          !customer || customer.kind === 'new' || customer.id !== appointment.customerId;
        if (customerChanged) {
          const part = buildCustomerPart();
          if (typeof part === 'string') {
            setBusy(false);
            return setError(part);
          }
          Object.assign(body, part);
        }
        await apiSend(`/api/admin/appointments/${appointment.id}`, 'PATCH', body);
      } else {
        const part = buildCustomerPart();
        if (typeof part === 'string') {
          setBusy(false);
          return setError(part);
        }
        await apiSend('/api/admin/appointments', 'POST', {
          ...part,
          staffId,
          date,
          startMin,
          serviceIds,
          status: requestDeposit ? 'PENDING' : status,
          applyDiscount,
          priceOverride: price ?? undefined,
          notes: notes.trim() || undefined,
          sendWhatsapp: notify,
          requestDeposit: requestDeposit || undefined,
          force,
        });
      }
      onSaved();
    } catch (e) {
      if (e instanceof ApiError && e.code === 'SLOT_CONFLICT') {
        const d = e.details as { conflicts?: Conflict[] } | undefined;
        setServerConflicts(d?.conflicts ?? [{ kind: 'STAFF', message: e.message }]);
        setConfirmForce(false);
      } else if (e instanceof ApiError && e.code === 'VERSION_MISMATCH') {
        setError('Bu randevu başka biri tarafından değiştirildi. Paneli kapatıp takvimi yenileyin.');
      } else {
        setError(e instanceof ApiError ? e.message : 'Kaydedilemedi.');
      }
    } finally {
      setBusy(false);
    }
  }

  const customerReady = Boolean(customer);
  const canSubmit = !busy && serviceIds.length > 0 && customerReady && (!hasConflict || manager);
  const verb = edit ? 'kaydet' : 'ekle';

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center md:items-center">
      <button
        type="button"
        aria-label="Kapat"
        className="absolute inset-0 bg-ink-900/40"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={edit ? 'Randevuyu düzenle' : 'Randevu ekle'}
        className="relative flex max-h-[94dvh] w-full max-w-xl flex-col rounded-t-2xl bg-white shadow-xl md:rounded-2xl"
      >
        <div className="flex items-center justify-between gap-3 border-b border-sand-200 px-4 py-3">
          <h2 className="text-base font-semibold">{edit ? 'Randevuyu düzenle' : 'Randevu ekle'}</h2>
          <button type="button" className="btn-ghost btn-sm" aria-label="Kapat" onClick={onClose}>
            <X size={16} strokeWidth={1.5} aria-hidden />
          </button>
        </div>

        <div className="space-y-5 overflow-y-auto px-4 py-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          {/* ---------------- Müşteri ---------------- */}
          <section className="space-y-2">
            <p className="label !mb-0">Müşteri</p>
            {customer?.kind === 'existing' ? (
              <div className="flex items-center justify-between gap-2 rounded-xl border border-sand-200 px-3 py-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold">{customer.label}</p>
                  <p className="muted text-xs">{formatPhone(customer.phone)}</p>
                </div>
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  onClick={() => setCustomer(null)}
                >
                  Değiştir
                </button>
              </div>
            ) : customer?.kind === 'new' ? (
              <div className="space-y-2 rounded-xl border border-sand-200 p-3">
                <div className="grid grid-cols-2 gap-2">
                  <input
                    className="field"
                    placeholder="Ad"
                    value={newFirst}
                    onChange={(e) => setNewFirst(e.target.value)}
                    aria-label="Ad"
                  />
                  <input
                    className="field"
                    placeholder="Soyad (isteğe bağlı)"
                    value={newLast}
                    onChange={(e) => setNewLast(e.target.value)}
                    aria-label="Soyad"
                  />
                </div>
                <PhoneInput id="manual-new-phone" onChange={setNewPhone} />
                <p className="muted text-xs">
                  Telefon zorunludur (bildirimler ve kayıt buna bağlıdır). Numara kayıtlıysa o müşteri
                  kullanılır.
                </p>
                <button type="button" className="btn-ghost btn-sm" onClick={() => setCustomer(null)}>
                  Kayıtlı müşteri ara
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="relative">
                  <Search
                    size={16}
                    strokeWidth={1.5}
                    className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-400"
                    aria-hidden
                  />
                  <input
                    className="field !pl-9"
                    placeholder="İsim veya telefon ara"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    aria-label="Müşteri ara"
                    autoComplete="off"
                  />
                </div>
                {found.length > 0 && (
                  <ul className="max-h-44 divide-y divide-sand-100 overflow-y-auto rounded-xl border border-sand-200">
                    {found.map((c) => (
                      <li key={c.id}>
                        <button
                          type="button"
                          className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left hover:bg-sand-100"
                          onClick={() => {
                            setCustomer({
                              kind: 'existing',
                              id: c.id,
                              label: `${c.firstName} ${c.lastName ?? ''}`.trim(),
                              phone: c.phone,
                            });
                            setQuery('');
                            setFound([]);
                          }}
                        >
                          <span className="truncate text-sm font-medium">
                            {c.firstName} {c.lastName ?? ''}
                          </span>
                          <span className="muted shrink-0 text-xs tabular-nums">{formatPhone(c.phone)}</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {query.trim().length >= 2 && found.length === 0 && (
                  <p className="muted text-xs">Sonuç yok.</p>
                )}
                <button type="button" className="btn-secondary btn-sm" onClick={() => setCustomer({ kind: 'new' })}>
                  + Yeni müşteri
                </button>
              </div>
            )}
          </section>

          {/* ---------------- Hizmetler ---------------- */}
          <section className="space-y-2">
            <p className="label !mb-0">Hizmetler</p>
            {groups.map((g) => (
              <div key={g.id} className="space-y-1.5">
                <p className="text-xs font-semibold text-ink-500">{g.name}</p>
                <div className="flex flex-wrap gap-1.5">
                  {g.services.map((s) => {
                    const unsupported = currentStaff ? !currentStaff.serviceIds.includes(s.id) : false;
                    const on = serviceIds.includes(s.id);
                    return (
                      <button
                        key={s.id}
                        type="button"
                        className="chip"
                        aria-pressed={on}
                        disabled={unsupported && !on}
                        title={unsupported ? `${currentStaff?.name} bu hizmeti yapmıyor` : undefined}
                        onClick={() => toggleService(s.id)}
                      >
                        {s.name}
                        <span className="text-xs text-ink-400">{formatTl(s.price)}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </section>

          {/* ---------------- Personel / tarih / saat ---------------- */}
          <section className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className="label" htmlFor="m-staff">
                Personel
              </label>
              <select
                id="m-staff"
                className="field"
                value={staffId}
                onChange={(e) => setStaffId(Number(e.target.value))}
              >
                {staff.map((s) => (
                  <option key={s.id} value={s.id} disabled={!manager && s.id !== viewer.id}>
                    {s.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label" htmlFor="m-date">
                Tarih
              </label>
              <input
                id="m-date"
                type="date"
                className="field"
                value={date}
                onChange={(e) => e.target.value && setDate(e.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="m-time">
                Saat
              </label>
              <select
                id="m-time"
                className="field tabular-nums"
                value={startMin}
                onChange={(e) => setStartMin(Number(e.target.value))}
              >
                {timeOptions.map((m) => (
                  <option key={m} value={m}>
                    {timeLabel(m)}
                  </option>
                ))}
              </select>
            </div>
          </section>

          {/* ---------------- Süre / fiyat önizleme ---------------- */}
          {previewError && (
            <p className="rounded-xl border border-danger-600/30 bg-danger-50 px-3 py-2 text-sm text-danger-700">
              {previewError}
            </p>
          )}
          {preview && (
            <div className="rounded-xl bg-sand-100 px-3 py-2.5 text-sm">
              <p className="tabular-nums">
                {timeLabel(startMin)}–{preview.endLabel} · {durationLabel(preview.totalMin)}
              </p>
              <p className="mt-0.5 font-semibold tabular-nums">
                {preview.discountRate > 0 && applyDiscount && priceText.trim() === '' ? (
                  <>
                    <span className="mr-1.5 font-normal text-ink-500 line-through">
                      {formatTl(preview.basePrice)}
                    </span>
                    {formatTl(preview.price)}
                    <span className="ml-1.5 text-xs font-normal text-success-700">
                      %{Math.round(preview.discountRate * 100)} fırsat saati indirimi
                    </span>
                  </>
                ) : (
                  formatTl(priceText.trim() === '' ? preview.price : Number(priceText.replace(',', '.')) || 0)
                )}
              </p>
            </div>
          )}

          {hasConflict && (
            <div className="space-y-2 rounded-xl border border-brass-300 bg-sand-100 px-3 py-2.5 text-sm">
              <p className="flex items-center gap-1.5 font-semibold text-brass-700">
                <AlertTriangle size={16} strokeWidth={1.5} aria-hidden /> Çakışma var
              </p>
              <ul className="list-disc space-y-0.5 pl-5 text-ink-900">
                {conflicts.map((c, i) => (
                  <li key={i}>{c.message}</li>
                ))}
              </ul>
              {!manager && (
                <p className="muted text-xs">Çakışmaya rağmen eklemek için yönetici yetkisi gerekir.</p>
              )}
              {manager && !confirmForce && (
                <button
                  type="button"
                  className="btn-secondary btn-sm"
                  disabled={busy || serviceIds.length === 0 || !customerReady}
                  onClick={() => setConfirmForce(true)}
                >
                  Yine de {verb}
                </button>
              )}
              {manager && confirmForce && (
                <div className="space-y-2 rounded-lg bg-white px-3 py-2">
                  <p className="text-sm">Randevu mevcut kayıtla üst üste binecek. Emin misiniz?</p>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="btn-danger btn-sm"
                      disabled={busy}
                      onClick={() => void submit(true)}
                    >
                      Evet, yine de {verb}
                    </button>
                    <button type="button" className="btn-ghost btn-sm" onClick={() => setConfirmForce(false)}>
                      Vazgeç
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ---------------- Fiyat / not / bildirim ---------------- */}
          <section className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="label" htmlFor="m-price">
                  Fiyat (elle)
                </label>
                <input
                  id="m-price"
                  className="field tabular-nums"
                  inputMode="decimal"
                  placeholder={edit ? `Şu an ${formatTl(appointment.totalPrice)}` : 'Otomatik'}
                  value={priceText}
                  onChange={(e) => setPriceText(e.target.value)}
                />
              </div>
              {!edit && (
                <div>
                  <label className="label" htmlFor="m-status">
                    Durum
                  </label>
                  <select
                    id="m-status"
                    className="field"
                    disabled={requestDeposit}
                    value={requestDeposit ? 'PENDING' : status}
                    onChange={(e) => setStatus(e.target.value as 'CONFIRMED' | 'PENDING')}
                  >
                    <option value="CONFIRMED">Onaylandı</option>
                    <option value="PENDING">Bekliyor</option>
                  </select>
                </div>
              )}
            </div>

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={applyDiscount}
                disabled={priceText.trim() !== ''}
                onChange={(e) => setApplyDiscount(e.target.checked)}
              />
              Salonun fırsat saati indirimini uygula (kural uygunsa)
            </label>

            <div>
              <label className="label" htmlFor="m-notes">
                Not
              </label>
              <textarea
                id="m-notes"
                className="field"
                rows={2}
                maxLength={500}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>

            {!edit && depositEnabled && (
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={requestDeposit}
                  onChange={(e) => setRequestDeposit(e.target.checked)}
                />
                <span>
                  Kapora iste
                  <span className="muted block text-xs">
                    Randevu “Kapora bekleniyor” olarak eklenir (saat dolu görünür); müşteriye IBAN’lı mesaj gider,
                    havale ulaşınca “Kapora ödendi” dersiniz.
                  </span>
                </span>
              </label>
            )}
            {edit && appointment.depositStatus === 'AWAITING' && (
              <p className="muted rounded-xl bg-sand-100 px-3 py-2 text-xs">
                Kapora bekleniyor: fiyat değişirse kapora tutarı yeniden hesaplanır. Mesaj otomatik tekrar
                gitmez; detaydan “Kapora mesajını tekrar gönder” diyebilirsiniz.
              </p>
            )}

            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={notify} onChange={(e) => setNotify(e.target.checked)} />
              {edit
                ? 'Müşteriye değişiklik mesajı gönder'
                : requestDeposit
                  ? 'Müşteriye kapora mesajı gönder'
                  : 'Müşteriye WhatsApp onayı gönder'}
            </label>
          </section>

          {error && (
            <p className="rounded-xl border border-danger-600/30 bg-danger-50 px-3 py-2 text-sm text-danger-700">
              {error}
            </p>
          )}

          <div className="flex gap-2">
            <button
              type="button"
              className="btn-primary flex-1"
              disabled={!canSubmit || (hasConflict && manager)}
              onClick={() => void submit(false)}
            >
              {busy ? 'Kaydediliyor…' : edit ? 'Kaydet' : 'Randevuyu ekle'}
            </button>
            <button type="button" className="btn-secondary" onClick={onClose}>
              Vazgeç
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
