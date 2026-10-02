'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Check, CircleAlert, CircleCheck, TriangleAlert } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  OpportunityBadge,
  ShadowBadge,
  ViewCountBadge,
} from '@/components/engagement/EngagementBadge';
import {
  ApiError,
  apiGet,
  apiSend,
  apiUpload,
  durationLabel,
  formatTl,
} from '@/lib/api-client';
import { CategoryIcon } from '@/components/marketing/CategoryIcon';

/* ------------------------------------------------------------------ */
/* Tipler — API sözleşmesinin istemci tarafı karşılığı                 */
/* ------------------------------------------------------------------ */

interface Category {
  id: number;
  name: string;
  slug: string;
  icon: string | null;
}

interface Service {
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
}

interface Slot {
  startMin: number;
  endMin: number;
  label: string;
  endLabel: string;
  isShadowFill: boolean;
  shadowParentAppointmentId?: number | null;
  discountRate: number;
  opportunityLabel: string;
  isOpportunity: boolean;
  viewCount: number;
  /** Bu saat şu anda BU ziyaretçi için tutuluyor (kendi soft-lock'u). */
  heldByYou?: boolean;
}

interface StaffAvailability {
  staffId: number;
  staffName: string;
  photoUrl: string | null;
  totalMin: number;
  totalPrice: number;
  savedMin: number;
  slots: Slot[];
  diagnostics: { requiredMin: number; longestFreeWindowMin: number; reason: string | null };
}

/** Ziyaretçinin açık kilidinin özeti (`yourLock` ve `/api/slots/lock/active`). */
interface ActiveLock {
  lockId: number;
  staffId: number;
  date: string;
  startMin: number;
  endMin: number;
  startLabel: string;
  endLabel: string;
  expiresAt: string;
}

interface AvailabilityResponse {
  date: string;
  package: {
    totalMin: number;
    totalPrice: number;
    savedMin: number;
    /** true → usta seçilmedi; süre nominal hızla (1.0) hesaplandı, ustaya göre değişir. */
    isNominal: boolean;
    /** Özetin hesaplandığı usta (usta seçilmediyse null). */
    basedOnStaffId: number | null;
    items: {
      serviceId: number;
      name: string;
      offsetMin: number;
      activeBeforeMin: number;
      passiveMin: number;
      activeAfterMin: number;
      placedInShadow: boolean;
    }[];
    shadowWindows: { start: number; end: number; minutes: number }[];
  };
  staff: StaffAvailability[];
  shadowUpsell: { serviceId: number; name: string; price: number; fitsWindowMin: number }[];
  /** Bu tarihte ziyaretçinin halihazırda tuttuğu saat (varsa). */
  yourLock: ActiveLock | null;
  message: string | null;
}

interface LockInfo {
  lockId: number;
  date: string;
  startMin: number;
  endMin: number;
  startLabel: string;
  endLabel: string;
  expiresAt: string;
  totalMin: number;
  totalPrice: number;
  savedMin: number;
}

type Step = 1 | 2 | 3 | 4 | 5;

type Chosen = { staff: StaffAvailability; slot: Slot };

const STEPS: { id: Step; label: string }[] = [
  { id: 1, label: 'Hizmet' },
  { id: 2, label: 'Usta' },
  { id: 3, label: 'Saat' },
  { id: 4, label: 'Görsel' },
  { id: 5, label: 'Onay' },
];

/** Tarih seçicide gösterilecek gün sayısı. */
const DAY_WINDOW = 14;

/** Tasarım görseli için üst sınır (sunucu da 8 MB'ı reddeder). */
const MAX_DESIGN_BYTES = 8 * 1024 * 1024;
const DESIGN_TYPES = ['image/jpeg', 'image/png', 'image/webp'];

function dateKey(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function dayChipLabel(key: string): { weekday: string; day: string } {
  const d = new Date(`${key}T00:00:00`);
  return {
    weekday: ['Paz', 'Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt'][d.getDay()],
    day: String(d.getDate()),
  };
}

/** Kilit alınamadığında kullanıcıya gösterilecek metin. */
function lockErrorMessage(e: unknown): string {
  if (e instanceof ApiError && e.code === 'SLOT_TAKEN') {
    const heldUntil = (e.details as { heldUntil?: string | null } | undefined)?.heldUntil;
    return heldUntil
      ? `Bu saat az önce alındı; ${new Date(heldUntil).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}'e kadar rezerve.`
      : 'Bu saat az önce başka bir müşteri tarafından alındı.';
  }
  return e instanceof ApiError ? e.message : 'Saat rezerve edilemedi.';
}

/** Bu kodlar "seçili saat artık kullanılamaz" demektir → 3. adıma dön. */
const SLOT_LOST_CODES = new Set([
  'SLOT_TAKEN',
  'SLOT_UNAVAILABLE',
  'LOCK_EXPIRED',
  'LOCK_NOT_FOUND',
  'FORBIDDEN',
  'CUSTOMER_OVERLAP',
]);

/* ------------------------------------------------------------------ */
/* Taslak — giriş (OTP) sayfasına gidip dönerken seçimler kaybolmasın  */
/* ------------------------------------------------------------------ */

/**
 * Misafir kullanıcı 5. adımda "Randevuyu onayla" dediğinde üye girişine
 * yönlendirilir. Eskiden `/randevu`'ya boş durumla dönülüyor ve hizmetler
 * YENİDEN seçiliyordu (şikâyetin asıl kaynağı). Artık seçimler sekmeye
 * özel `sessionStorage`'da tutulur; dönüşte kilit hâlâ geçerliyse doğrudan
 * onay adımına, süresi dolduysa aynı saat yeniden tutulmaya çalışılarak
 * kaldığı yere dönülür.
 *
 * Kilit sahipliği `visitor_key` çerezine bağlıdır ve giriş bu çerezi
 * değiştirmez; bu yüzden misafirken alınan kilit girişten sonra da
 * onaylanabilir (bkz. tests/test_booking_login_resume.py).
 *
 * Seçilen görsel DOSYASI saklanamaz (tarayıcı File nesnesini
 * serileştirmez); yalnızca "bir dosya seçilmişti" bilgisi saklanır ve
 * kullanıcıya yeniden eklemesi hatırlatılır.
 */
interface BookingDraft {
  v: 1;
  savedAt: number;
  serviceIds: number[];
  staffId: number | null;
  date: string;
  step: Step;
  chosen: Chosen | null;
  lock: LockInfo | null;
  notes: string;
  designLink: string;
  hadDesignFile: boolean;
}

const DRAFT_KEY = 'randevu-taslak-v1';
/** Bundan eski taslaklar geri yüklenmez. */
const DRAFT_MAX_AGE_MS = 2 * 60 * 60 * 1000;

function readDraft(): BookingDraft | null {
  try {
    const raw = window.sessionStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const draft = JSON.parse(raw) as BookingDraft;
    if (draft.v !== 1 || Date.now() - draft.savedAt > DRAFT_MAX_AGE_MS) return null;
    return draft;
  } catch {
    return null;
  }
}

function writeDraft(draft: Omit<BookingDraft, 'v' | 'savedAt'>) {
  try {
    const compact: BookingDraft = {
      ...draft,
      v: 1,
      savedAt: Date.now(),
      // Slot listesi saklanmaz: dönüşte zaten yeniden sorgulanır.
      chosen: draft.chosen ? { ...draft.chosen, staff: { ...draft.chosen.staff, slots: [] } } : null,
    };
    window.sessionStorage.setItem(DRAFT_KEY, JSON.stringify(compact));
  } catch {
    // Gizli sekme / kota: taslak olmadan da akış çalışır.
  }
}

function clearDraft() {
  try {
    window.sessionStorage.removeItem(DRAFT_KEY);
  } catch {
    /* yok say */
  }
}

/* ------------------------------------------------------------------ */

export function BookingFlow({
  categories,
  services,
  isMember,
  engagementOptIn,
  initialServiceIds,
  initialCategoryId,
  resumeRequested,
}: {
  categories: Category[];
  services: Service[];
  isMember: boolean;
  engagementOptIn: boolean;
  initialServiceIds: number[];
  initialCategoryId: number | null;
  /** `?resume=1` — girişten dönüldü, kayıtlı taslak geri yüklenecek. */
  resumeRequested: boolean;
}) {
  const router = useRouter();

  const [step, setStep] = useState<Step>(initialServiceIds.length ? 2 : 1);
  const [activeCategory, setActiveCategory] = useState<number | null>(
    initialCategoryId ?? categories[0]?.id ?? null,
  );
  const [selectedIds, setSelectedIds] = useState<number[]>(initialServiceIds);
  const [staffId, setStaffId] = useState<number | null>(null);
  const [date, setDate] = useState(dateKey(0));

  const [availability, setAvailability] = useState<AvailabilityResponse | null>(null);
  const [loadingSlots, setLoadingSlots] = useState(false);

  const [chosen, setChosen] = useState<Chosen | null>(null);
  const [lock, setLock] = useState<LockInfo | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);

  const [designLink, setDesignLink] = useState('');
  const [designFile, setDesignFile] = useState<File | null>(null);
  /** Girişe gidip dönerken seçilen dosya korunamadı → kullanıcıya hatırlat. */
  const [lostDesignFile, setLostDesignFile] = useState(false);
  const [notes, setNotes] = useState('');

  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** Taslak geri yüklenirken akış gösterilmez (1. adım titremesin). */
  const [restoring, setRestoring] = useState(resumeRequested);
  /** Taslak okunmadan yazılmasın diye: geri yükleme bitene kadar false. */
  const [hydrated, setHydrated] = useState(false);
  const [confirmed, setConfirmed] = useState<{
    id: number;
    startLabel: string;
    endLabel: string;
    staffName: string;
    serviceNames: string;
    totalPrice: number;
    discountRate: number;
    allergyWarnings: { label: string; severity: string; note: string | null }[];
    savedMin: number;
    designUploadFailed: boolean;
  } | null>(null);

  const selectedServices = useMemo(
    () => selectedIds.map((id) => services.find((s) => s.id === id)!).filter(Boolean),
    [selectedIds, services],
  );

  /** Sunucu hesabı gelene kadar gösterilecek KABA toplam (sıkıştırma hariç). */
  const naiveTotalMin = selectedServices.reduce(
    (sum, s) => sum + s.activeBeforeMin + s.passiveMin + s.activeAfterMin + s.bufferMin,
    0,
  );
  const naiveTotalPrice = selectedServices.reduce((sum, s) => sum + s.price, 0);

  const days = useMemo(() => Array.from({ length: DAY_WINDOW }, (_, i) => dateKey(i)), []);

  const loginHref = `/giris?next=${encodeURIComponent(
    `/randevu?resume=1&services=${selectedIds.join(',')}`,
  )}`;

  /* ---------------- Müsaitlik sorgusu ---------------- */

  /** Hızlı tarih değişiminde geç gelen ESKİ yanıt yenisini ezmesin. */
  const availabilitySeq = useRef(0);

  const loadAvailability = useCallback(async () => {
    if (selectedIds.length === 0) return;
    const seq = ++availabilitySeq.current;
    setLoadingSlots(true);
    try {
      const result = await apiSend<AvailabilityResponse>('/api/availability', 'POST', {
        date,
        serviceIds: selectedIds,
        staffId,
      });
      if (seq !== availabilitySeq.current) return;
      setAvailability(result);

      // Seçili saati TAZE veriyle eşle: hâlâ listede ise güncel nesneyi
      // kullan, listeden düştüyse seçimi kaldır. Hiç seçim yoksa ve
      // ziyaretçinin bu tarihte tuttuğu bir saat varsa onu ön-seç.
      setChosen((prev) => {
        const find = (sid: number, start: number): Chosen | null => {
          const staff = result.staff.find((s) => s.staffId === sid);
          const slot = staff?.slots.find((s) => s.startMin === start);
          return staff && slot ? { staff, slot } : null;
        };
        if (prev) return find(prev.staff.staffId, prev.slot.startMin);
        if (result.yourLock) return find(result.yourLock.staffId, result.yourLock.startMin);
        return null;
      });
    } catch (e) {
      if (seq !== availabilitySeq.current) return;
      setError(e instanceof ApiError ? e.message : 'Uygun saatler alınamadı.');
      setAvailability(null);
    } finally {
      if (seq === availabilitySeq.current) setLoadingSlots(false);
    }
  }, [date, selectedIds, staffId]);

  useEffect(() => {
    if (step === 3 && !restoring) void loadAvailability();
  }, [step, restoring, loadAvailability]);

  /* ---------------- Girişten dönüş: taslağı geri yükle ---------------- */

  useEffect(() => {
    let cancelled = false;
    const draft = readDraft();
    const usable =
      draft !== null &&
      // Yalnızca girişten dönüşte ya da açık bir kilit varken (sayfa
      // yenilendi) geri yüklenir; normal ziyarette temiz başlanır.
      (resumeRequested || draft.lock !== null) &&
      draft.serviceIds.length > 0 &&
      draft.serviceIds.every((id) => services.some((s) => s.id === id));

    if (!usable || !draft) {
      setRestoring(false);
      setHydrated(true);
      return;
    }

    const today = dateKey(0);
    const restoredDate = draft.date >= today ? draft.date : today;
    const sameDate = restoredDate === draft.date;

    setSelectedIds(draft.serviceIds);
    setStaffId(draft.staffId);
    setDate(restoredDate);
    setNotes(draft.notes);
    setDesignLink(draft.designLink);
    setLostDesignFile(draft.hadDesignFile);
    const firstService = services.find((s) => s.id === draft.serviceIds[0]);
    if (firstService?.categoryId) setActiveCategory(firstService.categoryId);

    const finish = () => {
      if (cancelled) return;
      setRestoring(false);
      setHydrated(true);
    };

    if (draft.chosen && draft.lock && sameDate) {
      const draftChosen = draft.chosen;
      const draftLock = draft.lock;
      const resumeStep: Step = draft.step >= 4 ? draft.step : 5;

      void (async () => {
        // 1) Kilit hâlâ bizim ve geçerli mi?
        let active: ActiveLock | null = null;
        try {
          active = (await apiGet<{ lock: ActiveLock | null }>('/api/slots/lock/active')).lock;
        } catch {
          active = null;
        }
        if (cancelled) return;

        if (active && active.lockId === draftLock.lockId) {
          setChosen(draftChosen);
          setLock({ ...draftLock, expiresAt: active.expiresAt });
          setStep(resumeStep);
          finish();
          return;
        }

        // 2) Süresi dolmuş: aynı saati yeniden tutmayı dene.
        try {
          const relocked = await apiSend<LockInfo>('/api/slots/lock', 'POST', {
            date: restoredDate,
            serviceIds: draft.serviceIds,
            staffId: draftChosen.staff.staffId,
            startMin: draftChosen.slot.startMin,
          });
          if (cancelled) return;
          setChosen(draftChosen);
          setLock(relocked);
          setStep(resumeStep);
          setNotice('Rezervasyon süren dolmuştu; aynı saati senin için yeniden tuttuk.');
        } catch (e) {
          if (cancelled) return;
          // 3) Saat artık uygun değil: hizmet/usta/tarih korunarak 3. adım.
          setChosen(null);
          setStep(3);
          setError(
            e instanceof ApiError && (e.code === 'SLOT_TAKEN' || e.code === 'SLOT_UNAVAILABLE')
              ? 'Tuttuğun saatin süresi doldu ve saat artık uygun değil. Seçimlerin korundu — lütfen yeni bir saat seç.'
              : lockErrorMessage(e),
          );
        }
        finish();
      })();
    } else {
      // Kilit yok: hizmet/usta/tarih korunur, saat seçimi 3. adımda
      // (seçili saat hâlâ uygunsa ön-seçili gelir).
      setChosen(sameDate ? draft.chosen : null);
      setStep(draft.chosen || draft.step >= 3 ? 3 : draft.step);
      finish();
    }

    return () => {
      cancelled = true;
    };
    // Yalnızca ilk yüklemede çalışır.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---------------- Taslağı güncel tut ---------------- */

  useEffect(() => {
    if (!hydrated || confirmed) return;
    if (selectedIds.length === 0) {
      clearDraft();
      return;
    }
    writeDraft({
      serviceIds: selectedIds,
      staffId,
      date,
      step,
      chosen,
      lock,
      notes,
      designLink,
      hadDesignFile: designFile !== null || lostDesignFile,
    });
  }, [
    hydrated,
    confirmed,
    selectedIds,
    staffId,
    date,
    step,
    chosen,
    lock,
    notes,
    designLink,
    designFile,
    lostDesignFile,
  ]);

  /* ---------------- Kilit geri sayımı ---------------- */

  useEffect(() => {
    if (!lock) return;
    const tick = () => {
      const remaining = Math.max(
        0,
        Math.floor((new Date(lock.expiresAt).getTime() - Date.now()) / 1000),
      );
      setSecondsLeft(remaining);
      if (remaining === 0) {
        // Süre doldu: kilit sunucuda zaten geçersiz, ekranı da geri al.
        // (Müsaitlik, 3. adıma geçişte efekt tarafından yeniden yüklenir.)
        setLock(null);
        setChosen(null);
        setNotice(null);
        setStep(3);
        setError('Rezervasyon süren doldu. Lütfen saati yeniden seç.');
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [lock]);

  /* ---------------- Eylemler ---------------- */

  /** Tutulan saati sunucuda bırakır ve ekrandan kaldırır. */
  async function dropLock() {
    const current = lock;
    if (!current) return;
    setLock(null);
    setNotice(null);
    await apiSend(`/api/slots/lock/${current.lockId}`, 'DELETE').catch(() => undefined);
  }

  /**
   * Geri gitme (alt çubuktaki "Geri" ve üstteki adım çubuğu).
   *
   * Hata düzeltmesi: eskiden yalnızca `setStep(s - 1)` yapılıyordu;
   * 4/5 → 3 ve öncesine dönüldüğünde kilit bırakılmıyor, geri sayım
   * arka planda sürüyor ve süre dolunca kullanıcı hangi adımdaysa
   * hatayla 3. adıma fırlatılıyordu. Artık saat seçimine (veya öncesine)
   * dönmek kilidi BIRAKIR; seçili saat 3. adımda işaretli kalır, tek
   * dokunuşla yeniden tutulabilir. 4 ↔ 5 arası gidişte kilit korunur.
   */
  async function goToStep(target: Step) {
    if (target >= step || busy) return;
    if (target <= 3 && lock) {
      setBusy(true);
      try {
        await dropLock();
      } finally {
        setBusy(false);
      }
    }
    setError(null);
    setStep(target);
  }

  function toggleService(id: number) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
    setAvailability(null);
    setChosen(null);
  }

  /**
   * "Beklerken bunları da yaptırabilirsin" önerisi. Öneri listesi ustadan
   * bağımsız hesaplanır; belirli bir usta seçiliyse ve o usta bu hizmeti
   * yapmıyorsa eklemek tüm saatleri yok ederdi — önce kontrol edilir.
   */
  async function addUpsell(serviceId: number) {
    setError(null);
    if (staffId !== null) {
      try {
        const result = await apiGet<{ staff: { id: number }[] }>(
          `/api/catalog/staff?serviceIds=${[...selectedIds, serviceId].join(',')}`,
        );
        if (!result.staff.some((s) => s.id === staffId)) {
          setError(
            'Seçtiğin usta bu hizmeti yapmıyor. Eklemek istersen usta adımında "Farketmez"i seçebilirsin.',
          );
          return;
        }
      } catch {
        // Kontrol yapılamadıysa eklemeye izin ver; müsaitlik yanıtı durumu açıklar.
      }
    }
    toggleService(serviceId);
  }

  async function selectSlot(staff: StaffAvailability, slot: Slot) {
    setChosen({ staff, slot });
    setError(null);

    // Engagement sayacı GERÇEK veriden beslensin diye görüntüleme kaydı.
    void apiSend('/api/slots/view', 'POST', {
      date,
      staffId: staff.staffId,
      startMin: slot.startMin,
    }).catch(() => undefined);
  }

  async function acquireLock() {
    if (!chosen) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await apiSend<LockInfo>('/api/slots/lock', 'POST', {
        date,
        serviceIds: selectedIds,
        staffId: chosen.staff.staffId,
        startMin: chosen.slot.startMin,
      });
      setLock(result);
      setStep(4);
    } catch (e) {
      setError(lockErrorMessage(e));
      if (e instanceof ApiError && SLOT_LOST_CODES.has(e.code)) {
        setChosen(null);
        await loadAvailability();
      }
    } finally {
      setBusy(false);
    }
  }

  async function releaseLock() {
    if (!lock) return;
    await dropLock();
    setStep(3);
  }

  /** Taslağı hemen yazıp giriş sayfasına gider; dönüşte 5. adıma dönülür. */
  function goToLogin() {
    writeDraft({
      serviceIds: selectedIds,
      staffId,
      date,
      step: 5,
      chosen,
      lock,
      notes,
      designLink,
      hadDesignFile: designFile !== null || lostDesignFile,
    });
    router.push(loginHref);
  }

  function pickDesignFile(file: File | null) {
    setError(null);
    if (file && !DESIGN_TYPES.includes(file.type)) {
      setError('Yalnızca JPG, PNG veya WEBP görsel yükleyebilirsin.');
      setDesignFile(null);
      return;
    }
    if (file && file.size > MAX_DESIGN_BYTES) {
      setError('Görsel en fazla 8 MB olabilir.');
      setDesignFile(null);
      return;
    }
    setDesignFile(file);
    if (file) setLostDesignFile(false);
  }

  async function confirm() {
    if (!lock || !chosen) return;
    // Misafir: sunucuya boşuna gitmeden, seçimleri saklayıp girişe yönlendir.
    if (!isMember) {
      goToLogin();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await apiSend<{
        appointment: {
          id: number;
          startLabel: string;
          endLabel: string;
          totalPrice: number;
          discountRate: number;
        };
        allergyWarnings: { label: string; severity: string; note: string | null }[];
        savedMin: number;
      }>('/api/appointments', 'POST', {
        lockId: lock.lockId,
        date,
        staffId: chosen.staff.staffId,
        startMin: chosen.slot.startMin,
        serviceIds: selectedIds,
        shadowParentId: chosen.slot.shadowParentAppointmentId ?? null,
        notes: notes || undefined,
        designLink: designLink || undefined,
      });

      // Dosya yüklemesi randevu oluştuktan SONRA yapılır (id gerekiyor).
      // Başarısızlık randevuyu bozmaz ama kullanıcıya SÖYLENİR.
      let designUploadFailed = false;
      if (designFile) {
        const form = new FormData();
        form.append('file', designFile);
        await apiUpload(`/api/appointments/${result.appointment.id}/design`, form).catch(() => {
          designUploadFailed = true;
        });
      }

      clearDraft();
      setLock(null);
      setConfirmed({
        id: result.appointment.id,
        startLabel: result.appointment.startLabel,
        endLabel: result.appointment.endLabel,
        staffName: chosen.staff.staffName,
        serviceNames: selectedServices.map((s) => s.name).join(' + '),
        totalPrice: result.appointment.totalPrice,
        discountRate: result.appointment.discountRate,
        allergyWarnings: result.allergyWarnings,
        savedMin: result.savedMin,
        designUploadFailed,
      });
      router.refresh();
    } catch (e) {
      if (e instanceof ApiError && e.code === 'MEMBERSHIP_REQUIRED') {
        goToLogin();
        return;
      }
      setError(e instanceof ApiError ? e.message : 'Randevu oluşturulamadı.');
      if (e instanceof ApiError && SLOT_LOST_CODES.has(e.code)) {
        // CUSTOMER_OVERLAP'ta kilit hâlâ geçerli: bırak ki saat boşa tutulmasın.
        if (e.code === 'CUSTOMER_OVERLAP') await dropLock();
        setLock(null);
        setChosen(null);
        setNotice(null);
        setStep(3);
      }
    } finally {
      setBusy(false);
    }
  }

  /* ---------------- Onay ekranı ---------------- */

  if (confirmed) {
    return (
      <div className="mx-auto max-w-md space-y-5 px-5 py-12 text-center">
        <div className="flex justify-center text-success-600" aria-hidden>
          <CircleCheck size={44} strokeWidth={1.5} />
        </div>
        <h1 className="display text-3xl">Randevun oluşturuldu</h1>
        <div className="card text-left">
          <p className="font-medium">
            {new Date(`${date}T00:00:00`).toLocaleDateString('tr-TR', {
              day: 'numeric',
              month: 'long',
              weekday: 'long',
            })}
          </p>
          <p className="muted">
            {confirmed.startLabel} – {confirmed.endLabel} · {confirmed.staffName}
          </p>
          <p className="mt-2">{confirmed.serviceNames}</p>
          <p className="mt-2 text-lg font-semibold tabular-nums">{formatTl(confirmed.totalPrice)}</p>
          {confirmed.discountRate > 0 && (
            <p className="muted">
              Fırsat saati indirimi: %{Math.round(confirmed.discountRate * 100)}
            </p>
          )}
          {confirmed.savedMin > 0 && (
            <p className="alert alert-success mt-2">
              <CircleCheck size={18} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
              <span>Paket sıkıştırması sayesinde {confirmed.savedMin} dakika erken çıkacaksın.</span>
            </p>
          )}
          {confirmed.designUploadFailed && (
            <p className="alert alert-warning mt-2">
              <TriangleAlert size={18} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
              <span>
                Randevun oluştu ama görselin yüklenemedi. Görseli randevuna gelirken
                ustana gösterebilirsin.
              </span>
            </p>
          )}
        </div>

        {confirmed.allergyWarnings.length > 0 && (
          <div className="alert alert-danger text-left">
            <TriangleAlert size={18} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
            <div>
            <p className="font-semibold">Kayıtlı alerji uyarın</p>
            <ul className="mt-1 space-y-1 text-sm">
              {confirmed.allergyWarnings.map((a) => (
                <li key={a.label}>
                  <strong>{a.label}</strong>
                  {a.note ? ` — ${a.note}` : ''}
                </li>
              ))}
            </ul>
            <p className="mt-2 text-xs">
              Bu uyarı ustaya da iletildi.
            </p>
            </div>
          </div>
        )}

        <div className="flex gap-2">
          <Link href="/hesabim" className="btn-primary flex-1">
            Randevularım
          </Link>
          <Link href="/" className="btn-secondary flex-1">
            Ana sayfa
          </Link>
        </div>
      </div>
    );
  }

  /* ---------------- Taslak geri yükleniyor ---------------- */

  if (restoring) {
    return (
      <div className="page-shell space-y-4 pt-6">
        <Stepper step={1} onJump={() => undefined} />
        <p className="muted">Seçimlerin geri yükleniyor…</p>
      </div>
    );
  }

  /* ---------------- Akış ---------------- */

  // Alt çubuktaki süre/tutar: en kesin bilgi hangisiyse o.
  // Kilit > seçilen ustanın hesabı > paket özeti (usta yoksa nominal) > kaba toplam.
  const barTotal = lock
    ? { min: lock.totalMin, price: lock.totalPrice, approx: false }
    : chosen
      ? { min: chosen.staff.totalMin, price: chosen.staff.totalPrice, approx: false }
      : availability
        ? {
            min: availability.package.totalMin,
            price: availability.package.totalPrice,
            approx: availability.package.isNominal,
          }
        : { min: naiveTotalMin, price: naiveTotalPrice, approx: true };

  return (
    <div className="page-shell space-y-4 pt-6">
      <Stepper step={step} onJump={(s) => void goToStep(s)} />

      {error && (
        <p className="alert alert-danger">
          <CircleAlert size={18} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </p>
      )}

      {notice && !error && (
        <p className="alert alert-success">
          <CircleCheck size={18} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
          <span>{notice}</span>
        </p>
      )}


      {/* ---------- 1) Hizmet seçimi ---------- */}
      {step === 1 && (
        <section className="space-y-3">
          <h1 className="display text-3xl md:text-4xl">Hangi hizmetleri istiyorsun?</h1>
          <p className="muted">
            Birden fazla seçebilirsin — sistem hepsini <strong>tek kesintisiz blok</strong> hâline
            getirir ve mümkünse birbirinin bekleme süresine yerleştirerek toplam süreyi kısaltır.
          </p>

          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
            {categories.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setActiveCategory(c.id)}
                className={`chip shrink-0 ${activeCategory === c.id ? 'chip-active' : ''}`}
              >
                <CategoryIcon slug={c.slug} /> {c.name}
              </button>
            ))}
          </div>

          <ul className="space-y-2">
            {services
              .filter((s) => s.categoryId === activeCategory)
              .map((service) => {
                const total =
                  service.activeBeforeMin +
                  service.passiveMin +
                  service.activeAfterMin +
                  service.bufferMin;
                const selected = selectedIds.includes(service.id);
                return (
                  <li key={service.id}>
                    <button
                      type="button"
                      onClick={() => toggleService(service.id)}
                      aria-pressed={selected}
                      className={`w-full rounded-[4px] border p-4 text-left transition-colors ${
                        selected
                          ? 'border-plum-600 bg-plum-50'
                          : 'border-sand-200 bg-white hover:border-ink-300'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-medium">{service.name}</p>
                          {service.description && (
                            <p className="mt-0.5 muted">{service.description}</p>
                          )}
                          <div className="mt-2 flex flex-wrap gap-1.5">
                            <span className="badge bg-sand-100 text-ink-700">
                              {durationLabel(total)}
                            </span>
                            {service.passiveMin > 0 && (
                              <span
                                className="badge bg-plum-50 text-plum-700"
                                title="Bu sürede usta serbest — araya başka bir işlem sığabilir"
                              >
                                {service.passiveMin} dk bekleme
                              </span>
                            )}
                            {service.shadowGuestAllowed && (
                              <span className="badge bg-success-50 text-success-700">
                                Ara saate sığar
                              </span>
                            )}
                          </div>
                        </div>
                        <span className="shrink-0 font-semibold tabular-nums">{formatTl(service.price)}</span>
                      </div>
                    </button>
                  </li>
                );
              })}
          </ul>
        </section>
      )}

      {/* ---------- 2) Usta seçimi ---------- */}
      {step === 2 && (
        <StaffPicker
          serviceIds={selectedIds}
          value={staffId}
          onChange={(id) => {
            if (id === staffId) return;
            setStaffId(id);
            setAvailability(null);
            setChosen(null);
          }}
        />
      )}

      {/* ---------- 3) Tarih + slot ---------- */}
      {step === 3 && (
        <section className="space-y-3">
          <h1 className="display text-3xl md:text-4xl">Ne zaman gelmek istersin?</h1>

          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1">
            {days.map((d) => {
              const chip = dayChipLabel(d);
              const active = d === date;
              return (
                <button
                  key={d}
                  type="button"
                  onClick={() => {
                    if (d === date) return;
                    setDate(d);
                    setChosen(null);
                    setError(null);
                  }}
                  className={`chip w-14 shrink-0 touch-target flex-col gap-0 py-2 ${
                    active ? 'chip-active chip-primary' : ''
                  }`}
                >
                  <span className="text-xs opacity-80">{chip.weekday}</span>
                  <span className="text-lg font-semibold tabular-nums">{chip.day}</span>
                </button>
              );
            })}
          </div>

          {availability && <PackageSummaryCard summary={availability.package} />}

          {loadingSlots && <p className="muted">Uygun saatler hesaplanıyor…</p>}

          {!loadingSlots && availability?.message && (
            <div className="alert alert-warning">
              <TriangleAlert size={18} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
              <span>{availability.message}</span>
            </div>
          )}

          {!loadingSlots &&
            availability?.staff.map((staff) => (
              <div key={staff.staffId} className="card">
                <div className="flex items-center justify-between">
                  <p className="font-medium">{staff.staffName}</p>
                  <span className="muted tabular-nums">
                    {durationLabel(staff.totalMin)} · {formatTl(staff.totalPrice)}
                  </span>
                </div>

                {staff.slots.length === 0 ? (
                  <p className="mt-2 muted">{staff.diagnostics.reason}</p>
                ) : (
                  <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
                    {staff.slots.map((slot) => {
                      const active =
                        chosen?.staff.staffId === staff.staffId &&
                        chosen.slot.startMin === slot.startMin;
                      return (
                        <button
                          key={slot.startMin}
                          type="button"
                          onClick={() => void selectSlot(staff, slot)}
                          aria-pressed={active}
                          title={slot.heldByYou ? 'Bu saat şu anda senin için tutuluyor' : undefined}
                          className={`chip chip-primary touch-target h-auto flex-col gap-0 px-1 py-2 ${
                            active
                              ? 'chip-active'
                              : slot.heldByYou
                                ? 'border-plum-400 bg-plum-50 hover:border-plum-600'
                                : ''
                          }`}
                        >
                          <span className="font-semibold tabular-nums">{slot.label}</span>
                          <span
                            className={`text-[10px] ${active ? 'text-plum-100' : 'text-ink-500'}`}
                          >
                            {slot.endLabel}'e kadar
                          </span>
                          <span className="mt-1 flex flex-wrap justify-center gap-0.5">
                            {slot.heldByYou && (
                              <span
                                className={`badge ${active ? 'bg-white/20 text-white' : 'bg-plum-100 text-plum-700'}`}
                              >
                                Senin için tutuluyor
                              </span>
                            )}
                            {slot.isShadowFill && <ShadowBadge />}
                            <OpportunityBadge
                              discountRate={slot.discountRate}
                              label={slot.opportunityLabel}
                            />
                            <ViewCountBadge count={slot.viewCount} optIn={engagementOptIn} />
                          </span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}

          {availability && availability.shadowUpsell.length > 0 && (
            <div className="card border-plum-200 bg-plum-50">
              <p className="font-medium text-plum-700">Beklerken bunları da yaptırabilirsin</p>
              <p className="muted">
                Paketinde ustanın serbest kaldığı bir pencere var; bu hizmetler oraya sığıyor.
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                {availability.shadowUpsell.map((u) => (
                  <button
                    key={u.serviceId}
                    type="button"
                    onClick={() => void addUpsell(u.serviceId)}
                    className="btn-secondary"
                  >
                    + {u.name} ({formatTl(u.price)})
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      )}

      {/* ---------- 4) Tasarım görseli ---------- */}
      {step === 4 && lock && (
        <section className="space-y-3">
          <h1 className="display text-3xl md:text-4xl">İstediğin bir model var mı?</h1>
          <p className="muted">
            İsteğe bağlı. Bir görsel yükleyebilir veya Pinterest/Instagram bağlantısı
            yapıştırabilirsin — ustan randevudan önce görür.
          </p>

          <CountdownBar secondsLeft={secondsLeft} onCancel={() => void releaseLock()} />

          {!isMember && <MembershipHint loginHref={loginHref} />}

          <div className="card space-y-3">
            <div>
              <label className="label" htmlFor="designFile">
                Görsel yükle
              </label>
              <input
                id="designFile"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={(e) => pickDesignFile(e.target.files?.[0] ?? null)}
                className="field"
              />
              <p className="mt-1 muted">JPG, PNG veya WEBP · en fazla 8 MB</p>
              {designFile && <p className="mt-1 text-sm text-ink-700">Seçili: {designFile.name}</p>}
              {lostDesignFile && !designFile && (
                <p className="mt-1 text-sm text-warning-600">
                  Giriş sırasında seçtiğin görsel korunamadı (tarayıcı dosyaları saklayamaz).
                  İstersen yeniden ekleyebilirsin.
                </p>
              )}
            </div>

            <div>
              <label className="label" htmlFor="designLink">
                veya bağlantı yapıştır
              </label>
              <input
                id="designLink"
                className="field"
                value={designLink}
                onChange={(e) => setDesignLink(e.target.value)}
                placeholder="https://pinterest.com/pin/..."
                inputMode="url"
              />
            </div>

            <div>
              <label className="label" htmlFor="notes">
                Ustaya not (isteğe bağlı)
              </label>
              <textarea
                id="notes"
                className="field"
                rows={3}
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Örn. çok kısa olmasın"
              />
            </div>
          </div>
        </section>
      )}

      {/* ---------- 5) Özet ---------- */}
      {step === 5 && lock && chosen && (
        <section className="space-y-3">
          <h1 className="display text-3xl md:text-4xl">Son kontrol</h1>
          <CountdownBar secondsLeft={secondsLeft} onCancel={() => void releaseLock()} />

          <div className="card space-y-2">
            <Row label="Tarih" value={new Date(`${date}T00:00:00`).toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', weekday: 'long' })} />
            <Row label="Saat" value={`${lock.startLabel} – ${lock.endLabel}`} />
            <Row label="Usta" value={chosen.staff.staffName} />
            <Row label="Hizmetler" value={selectedServices.map((s) => s.name).join(' + ')} />
            <Row label="Toplam süre" value={durationLabel(lock.totalMin)} />
            {(notes || designLink || designFile) && (
              <Row
                label="Ustaya iletilecek"
                value={[
                  designFile ? 'görsel' : null,
                  designLink ? 'bağlantı' : null,
                  notes ? 'not' : null,
                ]
                  .filter(Boolean)
                  .join(', ')}
              />
            )}
            <Row label="Tutar" value={formatTl(lock.totalPrice)} />
            {chosen.slot.discountRate > 0 && (
              <Row
                label="Fırsat indirimi"
                value={`%${Math.round(chosen.slot.discountRate * 100)} — ${formatTl(lock.totalPrice * (1 - chosen.slot.discountRate))}`}
              />
            )}
            {lock.savedMin > 0 && (
              <p className="alert alert-success">
                <CircleCheck size={18} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
                <span>Sıkıştırma sayesinde {lock.savedMin} dakika kazandın.</span>
              </p>
            )}
            {chosen.slot.isShadowFill && (
              <p className="rounded-[2px] bg-plum-50 px-3 py-2 text-sm text-plum-700">
                Bu saat, ustanın başka bir işlemde beklediği süreye denk geliyor. Salon için
                verimli, senin için erken bir saat.
              </p>
            )}
          </div>

          {lostDesignFile && !designFile && (
            <div className="alert alert-warning">
              <TriangleAlert size={18} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
              <div>
                Giriş sırasında seçtiğin görsel korunamadı.{' '}
                <button
                  type="button"
                  className="font-semibold underline"
                  onClick={() => void goToStep(4)}
                >
                  Görseli yeniden ekle
                </button>{' '}
                (tuttuğun saat korunur).
              </div>
            </div>
          )}

          {!isMember && <MembershipHint loginHref={loginHref} />}
        </section>
      )}

      {/* ---------- Alt eylem çubuğu ---------- */}
      <div className="sticky bottom-20 z-10 md:bottom-4">
        <div className="rounded-[4px] border border-sand-200 bg-white p-3">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="muted">
              {selectedIds.length === 0
                ? 'Hizmet seçilmedi'
                : `${selectedIds.length} hizmet · ${barTotal.approx ? 'yaklaşık ' : ''}${durationLabel(barTotal.min)}`}
            </span>
            <span className="font-semibold tabular-nums">{formatTl(barTotal.price)}</span>
          </div>

          <div className="flex gap-2">
            {step > 1 && (
              <button
                type="button"
                className="btn-secondary flex-1"
                disabled={busy}
                onClick={() => void goToStep((step - 1) as Step)}
              >
                Geri
              </button>
            )}

            {step === 1 && (
              <button
                type="button"
                className="btn-primary flex-1"
                disabled={selectedIds.length === 0}
                onClick={() => setStep(2)}
              >
                Devam
              </button>
            )}
            {step === 2 && (
              <button type="button" className="btn-primary flex-1" onClick={() => setStep(3)}>
                Saatleri gör
              </button>
            )}
            {step === 3 && (
              <button
                type="button"
                className="btn-primary flex-1"
                disabled={!chosen || busy}
                onClick={() => void acquireLock()}
              >
                {busy ? 'Rezerve ediliyor…' : 'Bu saati tut'}
              </button>
            )}
            {step === 4 && (
              <button type="button" className="btn-primary flex-1" onClick={() => setStep(5)}>
                Özete geç
              </button>
            )}
            {step === 5 && (
              <button
                type="button"
                className="btn-primary flex-1"
                disabled={busy}
                onClick={() => void confirm()}
              >
                {busy ? 'Onaylanıyor…' : isMember ? 'Randevuyu onayla' : 'Giriş yap ve onayla'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Alt bileşenler                                                      */
/* ------------------------------------------------------------------ */

function Stepper({ step, onJump }: { step: Step; onJump: (s: Step) => void }) {
  return (
    <ol className="flex items-start gap-3">
      {STEPS.map((s) => {
        const state = s.id === step ? 'current' : s.id < step ? 'done' : 'todo';
        return (
          <li key={s.id} className="flex-1">
            <button
              type="button"
              onClick={() => onJump(s.id)}
              disabled={state === 'todo'}
              className="w-full text-left"
            >
              <div
                className={`${state === 'current' ? 'h-0.5' : 'h-px'} ${
                  state === 'todo' ? 'bg-sand-300' : 'bg-plum-600'
                }`}
              />
              <span
                className={`mt-2 flex items-center gap-1.5 text-[11px] font-semibold uppercase ${
                  state === 'current'
                    ? 'text-ink-900'
                    : state === 'done'
                      ? 'text-plum-600'
                      : 'text-ink-400'
                }`}
                style={{ letterSpacing: '0.12em' }}
              >
                {state === 'done' ? (
                  <Check size={12} strokeWidth={2} aria-hidden />
                ) : (
                  <span className="tabular-nums" aria-hidden>
                    {s.id}
                  </span>
                )}
                {s.label}
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}

/**
 * Paketin zaman çizelgesi. Aktif dilimler dolu, pasif (bekleme)
 * dilimler ÇİZGİLİ gösterilir — müşteri "bu 40 dakika beklemem" ile
 * "usta bu 40 dakikada başkasıyla ilgilenebilir"i aynı anda görür.
 */
function PackageSummaryCard({
  summary,
}: {
  summary: AvailabilityResponse['package'];
}) {
  if (summary.totalMin === 0) return null;

  return (
    <div className="card">
      <div className="flex items-baseline justify-between">
        <p className="font-medium">
          Toplam {summary.isNominal ? 'yaklaşık ' : ''}
          {durationLabel(summary.totalMin)}
        </p>
        <p className="font-semibold tabular-nums">{formatTl(summary.totalPrice)}</p>
      </div>

      {summary.isNominal && (
        <p className="mt-1 muted">
          Usta seçmediğin için süre ortalama hıza göre hesaplandı; kesin süre her ustanın
          yanında yazıyor.
        </p>
      )}

      {summary.savedMin > 0 && (
        <p className="mt-1 text-sm text-success-700">
          Sıkıştırma ile {summary.savedMin} dakika kazanç — hizmetler birbirinin bekleme
          süresine yerleşti.
        </p>
      )}

      <div className="mt-3 flex h-8 w-full overflow-hidden rounded-[2px] border border-sand-200">
        {summary.items.map((item) => {
          const seg = (min: number) => `${(min / summary.totalMin) * 100}%`;
          return (
            <div key={`${item.serviceId}-${item.offsetMin}`} className="contents">
              {item.activeBeforeMin > 0 && (
                <div
                  className="bg-plum-500"
                  style={{ width: seg(item.activeBeforeMin) }}
                  title={`${item.name} — usta meşgul (${item.activeBeforeMin} dk)`}
                />
              )}
              {item.passiveMin > 0 && (
                <div
                  className="shadow-window"
                  style={{ width: seg(item.passiveMin) }}
                  title={`${item.name} — bekleme, usta serbest (${item.passiveMin} dk)`}
                />
              )}
              {item.activeAfterMin > 0 && (
                <div
                  className="bg-plum-500"
                  style={{ width: seg(item.activeAfterMin) }}
                  title={`${item.name} — usta meşgul (${item.activeAfterMin} dk)`}
                />
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-2 flex gap-3 text-xs text-ink-500">
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-4 rounded-[2px] bg-plum-500" /> usta meşgul
        </span>
        <span className="flex items-center gap-1">
          <span className="shadow-window inline-block h-2.5 w-4 rounded-[2px]" /> bekleme (usta serbest)
        </span>
      </div>
    </div>
  );
}

function StaffPicker({
  serviceIds,
  value,
  onChange,
}: {
  serviceIds: number[];
  value: number | null;
  onChange: (id: number | null) => void;
}) {
  const [staff, setStaff] = useState<
    { id: number; name: string; photoUrl: string | null; speedFactor: number }[]
  >([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`/api/catalog/staff?serviceIds=${serviceIds.join(',')}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((body) => {
        if (cancelled || !body.ok) return;
        const list = body.data.staff as { id: number }[];
        setStaff(body.data.staff);
        // Hizmetler değişti ve seçili usta artık hepsini yapamıyor:
        // seçimi "Farketmez"e çek, aksi halde 3. adımda hiç saat çıkmaz.
        if (value !== null && !list.some((s) => s.id === value)) onChange(null);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
    // Yalnızca hizmet listesi değiştiğinde yeniden sorgulanır.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serviceIds]);

  return (
    <section className="space-y-3">
      <h1 className="display text-3xl md:text-4xl">Kiminle çalışmak istersin?</h1>
      <p className="muted">
        Yalnızca seçtiğin hizmetlerin <strong>tamamını</strong> yapabilen ustalar listelenir.
      </p>

      {loading && <p className="muted">Yükleniyor…</p>}

      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        <button
          type="button"
          onClick={() => onChange(null)}
          className={`card text-left ${value === null ? 'border-plum-600 bg-plum-50' : 'hover:border-ink-300'}`}
        >
          <p className="font-medium">Farketmez</p>
          <p className="muted">En uygun saatleri bulmak için tüm ustalar taranır.</p>
        </button>

        {staff.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => onChange(s.id)}
            className={`card flex items-center gap-3 text-left ${
              value === s.id ? 'border-plum-600 bg-plum-50' : 'hover:border-ink-300'
            }`}
          >
            {s.photoUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={s.photoUrl} alt="" className="h-12 w-12 rounded-full object-cover" />
            ) : (
              <span className="grid h-12 w-12 place-items-center rounded-full bg-sand-200">
                {s.name[0]}
              </span>
            )}
            <div>
              <p className="font-medium">{s.name}</p>
              {s.speedFactor < 1 && <p className="muted">Bu işi ortalamadan hızlı tamamlıyor</p>}
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}

/** Soft-lock geri sayımı — kullanıcı ne kadar süresi kaldığını görür. */
function CountdownBar({
  secondsLeft,
  onCancel,
}: {
  secondsLeft: number;
  onCancel: () => void;
}) {
  const minutes = Math.floor(secondsLeft / 60);
  const seconds = secondsLeft % 60;
  const urgent = secondsLeft < 60;

  return (
    <div
      className={`flex items-center justify-between rounded-[2px] border px-4 py-3 text-sm ${
        urgent
          ? 'border-danger-600/30 bg-danger-50 text-danger-700'
          : 'border-plum-200 bg-plum-50 text-plum-700'
      }`}
    >
      <span>
        Bu saat senin için tutuldu ·{' '}
        <strong className="tabular-nums">
          {minutes}:{String(seconds).padStart(2, '0')}
        </strong>
      </span>
      <button type="button" onClick={onCancel} className="btn-link">
        Vazgeç
      </button>
    </div>
  );
}

/**
 * Misafire ÖNCEDEN söylenir: onay için giriş gerekecek, ama seçimler ve
 * tutulan saat korunur — girişten sonra doğrudan onay adımına dönülür.
 */
function MembershipHint({ loginHref }: { loginHref: string }) {
  return (
    <div className="alert alert-warning">
      <TriangleAlert size={18} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
      <div>
      Randevuyu tamamlamak için üye girişi gerekiyor (şifresiz, telefonuna gelen kodla).
      Seçimlerin ve tuttuğun saat korunur; girişten sonra doğrudan onay adımına dönersin.{' '}
      <Link href={loginHref} className="font-semibold underline">
        Giriş yap
      </Link>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-sand-100 pb-2 last:border-0">
      <span className="muted">{label}</span>
      <span className="text-right font-medium tabular-nums">{value}</span>
    </div>
  );
}
