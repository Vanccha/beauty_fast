'use client';

import { Check, CircleCheck, Minus, Plus, TriangleAlert, UserPlus, X } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { NameEditor } from '@/components/auth/NameEditor';
import { PhoneVerify, type VerifiedCustomer } from '@/components/auth/PhoneVerify';
import { CategoryIcon } from '@/components/marketing/CategoryIcon';
import { ApiError, apiSend, durationLabel, formatTl, timeLabel } from '@/lib/api-client';
import { formatDateTr } from '@/lib/time';

/* ------------------------------------------------------------------ */
/* Tipler                                                              */
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
}

interface Person {
  key: number;
  firstName: string;
  phone: string;
  serviceIds: number[];
  staffId: number | null;
  notes: string;
}

interface Assignment {
  personIndex: number;
  staffId: number;
  staffName: string;
  startMin: number;
  endMin: number;
  totalMin: number;
  totalPrice: number;
}

interface GroupOption {
  startMin: number;
  assignments: Assignment[];
}

interface GroupAvailability {
  options: GroupOption[];
  suggestDates: { date: string; optionCount: number }[];
}

interface GroupLock {
  groupId: string;
  expiresAt: string;
  ttlSeconds: number;
  locks: {
    personIndex: number;
    lockId: number;
    staffId: number;
    startMin: number;
    endMin: number;
    totalPrice: number;
  }[];
}

interface CreatedGroup {
  groupId: string;
  appointments: {
    personIndex: number;
    appointmentId: number;
    forCustomer: { id: number; firstName: string };
    staffName: string;
    date: string;
    startMin: number;
    endMin: number;
    totalPrice: number;
  }[];
  totalPrice: number;
}

type Step = 1 | 2 | 3 | 4;

const STEPS: { id: Step; label: string }[] = [
  { id: 1, label: 'Kişiler' },
  { id: 2, label: 'Hizmetler' },
  { id: 3, label: 'Saat' },
  { id: 4, label: 'Onay' },
];

const MAX_PEOPLE = 4;
const MIN_PEOPLE = 2;
const DAY_WINDOW = 14;

/** "seçili saat artık kullanılamaz" anlamına gelen kodlar → 3. adıma dön. */
const SLOT_LOST_CODES = new Set([
  'SLOT_TAKEN',
  'SLOT_UNAVAILABLE',
  'LOCK_EXPIRED',
  'LOCK_NOT_FOUND',
  'FORBIDDEN',
  'CUSTOMER_OVERLAP',
]);

/* ------------------------------------------------------------------ */
/* Yardımcılar                                                         */
/* ------------------------------------------------------------------ */

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

/** "0532 000 00 00" / "+90 532..." → "5320000000" (karşılaştırma için). */
function normalizePhone(raw: string): string {
  let d = raw.replace(/\D/g, '');
  if (d.startsWith('90') && d.length === 12) d = d.slice(2);
  if (d.startsWith('0')) d = d.slice(1);
  return d;
}

function phoneValid(raw: string): boolean {
  return /^5\d{9}$/.test(normalizePhone(raw));
}

function serviceTotalMin(s: Service): number {
  return s.activeBeforeMin + s.passiveMin + s.activeAfterMin + s.bufferMin;
}

let personKeySeq = 0;
function newPerson(partial: Partial<Person> = {}): Person {
  personKeySeq += 1;
  return { key: personKeySeq, firstName: '', phone: '', serviceIds: [], staffId: null, notes: '', ...partial };
}

/* ------------------------------------------------------------------ */
/* Ana bileşen                                                         */
/* ------------------------------------------------------------------ */

export function GroupFlow({
  categories,
  services,
  initialCustomer,
  initialServiceIds,
}: {
  categories: Category[];
  services: Service[];
  initialCustomer: VerifiedCustomer | null;
  initialServiceIds: number[];
}) {
  const [customer, setCustomer] = useState<VerifiedCustomer | null>(initialCustomer);

  const [step, setStep] = useState<Step>(1);
  const [includeSelf, setIncludeSelf] = useState(true);
  const [people, setPeople] = useState<Person[]>(() => [
    newPerson({ serviceIds: initialServiceIds }),
    newPerson(),
  ]);

  const [date, setDate] = useState(() => dateKey(0));
  const [availability, setAvailability] = useState<GroupAvailability | null>(null);
  const [loadingAvail, setLoadingAvail] = useState(false);
  const [chosenStart, setChosenStart] = useState<number | null>(null);

  const [lock, setLock] = useState<GroupLock | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [created, setCreated] = useState<CreatedGroup | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);

  const serviceById = useMemo(() => new Map(services.map((s) => [s.id, s])), [services]);

  /* ---------- Kişi doğrulama ---------- */

  const selfPhone = customer ? normalizePhone(customer.phone) : '';

  function personError(p: Person, index: number): string | null {
    if (includeSelf && index === 0) return null;
    if (p.firstName.trim().length < 1) return 'Ad gerekli.';
    if (!phoneValid(p.phone)) return 'Geçerli bir cep telefonu gir (05xx...).';
    const n = normalizePhone(p.phone);
    if (n === selfPhone) return 'Bu numara senin numaran; "Ben de katılıyorum" seçeneğini kullan.';
    const dup = people.some(
      (o, i) => i !== index && !(includeSelf && i === 0) && normalizePhone(o.phone) === n,
    );
    if (dup) return 'Bu numara grupta zaten var.';
    return null;
  }

  const step1Valid = people.length >= MIN_PEOPLE && people.every((p, i) => personError(p, i) === null);
  const step2Valid = people.every((p) => p.serviceIds.length > 0);

  /* ---------- Müsaitlik ---------- */

  const peopleSig = JSON.stringify(people.map((p) => [p.serviceIds, p.staffId]));
  const [refreshTick, setRefreshTick] = useState(0);

  useEffect(() => {
    if (step !== 3 || !customer) return;
    let cancelled = false;
    setLoadingAvail(true);
    setAvailability(null);
    setChosenStart(null);
    apiSend<GroupAvailability>('/api/availability/group', 'POST', {
      date,
      people: people.map((p) => ({ serviceIds: p.serviceIds, staffId: p.staffId })),
    })
      .then((r) => {
        if (!cancelled) setAvailability(r);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : 'Saatler getirilemedi.');
      })
      .finally(() => {
        if (!cancelled) setLoadingAvail(false);
      });
    return () => {
      cancelled = true;
    };
    // people yalnızca imzası değişince yeniden sorgulanır; refreshTick 409 sonrası tazeler.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [step, date, peopleSig, customer, refreshTick]);

  /* ---------- Kilit ve geri sayım ---------- */

  const lockRef = useRef<GroupLock | null>(null);
  lockRef.current = lock;
  const doneRef = useRef(false);
  doneRef.current = created !== null;

  const releaseLock = useCallback(async () => {
    const current = lockRef.current;
    if (!current) return;
    setLock(null);
    lockRef.current = null;
    await apiSend(`/api/slots/lock-group/${current.groupId}`, 'DELETE').catch(() => undefined);
  }, []);

  // Sayfadan ayrılırken (onaylanmadıysa) kilidi bırak.
  useEffect(() => {
    return () => {
      const current = lockRef.current;
      if (current && !doneRef.current) {
        void fetch(`/api/slots/lock-group/${current.groupId}`, {
          method: 'DELETE',
          keepalive: true,
        }).catch(() => undefined);
      }
    };
  }, []);

  useEffect(() => {
    if (!lock) return;
    const tick = () => {
      const left = Math.max(0, Math.floor((new Date(lock.expiresAt).getTime() - Date.now()) / 1000));
      setSecondsLeft(left);
      if (left === 0) {
        setLock(null);
        setStep(3);
        setWarning('Tutma süresi doldu. Saatleri yeniden seçebilirsin.');
        setRefreshTick((t) => t + 1);
      }
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [lock]);

  /* ---------- Eylemler ---------- */

  const chosenOption = availability?.options.find((o) => o.startMin === chosenStart) ?? null;

  function updatePerson(index: number, patch: Partial<Person>) {
    setPeople((prev) => prev.map((p, i) => (i === index ? { ...p, ...patch } : p)));
  }

  function personBody(p: Person, index: number) {
    if (includeSelf && index === 0) return { self: true as const };
    return { beneficiary: { firstName: p.firstName.trim(), phone: p.phone.trim() } };
  }

  function goBack() {
    setError(null);
    setWarning(null);
    if (step === 4) {
      void releaseLock();
      setStep(3);
    } else if (step > 1) {
      setStep((step - 1) as Step);
    }
  }

  async function acquireLock() {
    if (!chosenOption) return;
    setBusy(true);
    setError(null);
    setWarning(null);
    try {
      const result = await apiSend<GroupLock>('/api/slots/lock-group', 'POST', {
        date,
        startMin: chosenOption.startMin,
        people: people.map((p, i) => {
          const a = chosenOption.assignments.find((x) => x.personIndex === i);
          return { serviceIds: p.serviceIds, staffId: a?.staffId, ...personBody(p, i) };
        }),
      });
      setLock(result);
      setStep(4);
    } catch (e) {
      if (e instanceof ApiError && e.code === 'SLOT_TAKEN') {
        setWarning('Bu saat az önce doldu. Güncel ortak saatler yenilendi.');
        setRefreshTick((t) => t + 1);
      } else {
        setError(e instanceof ApiError ? e.message : 'Saatler tutulamadı.');
      }
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    if (!lock) return;
    setBusy(true);
    setError(null);
    setWarning(null);
    try {
      const result = await apiSend<CreatedGroup>('/api/appointments/group', 'POST', {
        groupId: lock.groupId,
        people: people.map((p, i) => {
          const l = lock.locks.find((x) => x.personIndex === i);
          return {
            lockId: l?.lockId,
            ...personBody(p, i),
            ...(p.notes.trim() ? { notes: p.notes.trim() } : {}),
          };
        }),
      });
      doneRef.current = true;
      lockRef.current = null;
      setLock(null);
      setCreated(result);
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        setWarning('Çok fazla deneme yaptın. Lütfen biraz sonra tekrar dene.');
      } else if (e instanceof ApiError && (SLOT_LOST_CODES.has(e.code) || e.status === 409)) {
        setLock(null);
        lockRef.current = null;
        setStep(3);
        setWarning('Seçtiğin saat artık uygun değil. Lütfen yeni bir ortak saat seç.');
        setRefreshTick((t) => t + 1);
      } else {
        setError(e instanceof ApiError ? e.message : 'Randevular oluşturulamadı.');
      }
    } finally {
      setBusy(false);
    }
  }

  function toggleSelf(on: boolean) {
    setIncludeSelf(on);
    // Kart 1 normal bir kişi olur (ya da tersi); kişisel alanlar temizlenir.
    updatePerson(0, { firstName: '', phone: '' });
  }

  // Yeni eklenen kartın ad alanına odaklanılır (sayfa o karta kayar).
  const focusKey = useRef<number | null>(null);
  useEffect(() => {
    if (focusKey.current === null) return;
    const input = document.getElementById(`g-name-${focusKey.current}`);
    focusKey.current = null;
    if (input) {
      input.focus({ preventScroll: true });
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      input.closest('li')?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'center' });
    }
  }, [people.length]);

  function addPerson() {
    if (people.length >= MAX_PEOPLE) return;
    const person = newPerson();
    focusKey.current = person.key;
    setPeople((prev) => [...prev, person]);
  }

  function removePerson(index: number) {
    if (people.length <= MIN_PEOPLE) return;
    setPeople((prev) => prev.filter((_, i) => i !== index));
  }

  /** Kişi sayısını doğrudan ayarlar. Azaltırken önce BOŞ kartlar çıkarılır;
   *  yazılmış bilgiler ancak boş kart kalmazsa (sondan) gider. 1. kart hep kalır. */
  function setPeopleCount(target: number) {
    const count = Math.min(MAX_PEOPLE, Math.max(MIN_PEOPLE, target));
    if (count === people.length) return;
    if (count > people.length) {
      const added = Array.from({ length: count - people.length }, () => newPerson());
      focusKey.current = added[0].key;
      setPeople((prev) => [...prev, ...added]);
      return;
    }
    const isEmpty = (p: Person) => !p.firstName.trim() && !p.phone.trim() && p.serviceIds.length === 0;
    setPeople((prev) => {
      const next = [...prev];
      while (next.length > count) {
        let drop = next.length - 1;
        for (let i = next.length - 1; i > 0; i--) {
          if (isEmpty(next[i])) {
            drop = i;
            break;
          }
        }
        next.splice(drop, 1);
      }
      return next;
    });
  }

  /* ---------- Ekranlar ---------- */

  if (!customer) {
    return (
      <div className="page-shell py-6">
        <PhoneVerify
          onVerified={setCustomer}
          title="Grup randevusu"
          description="Grubu oluşturmak için önce kendi numaranı doğrula. Diğer kişilere WhatsApp ile bilgi gönderilir."
        />
      </div>
    );
  }

  if (created) {
    return (
      <section className="page-shell !max-w-xl space-y-6 py-6">
        <div className="text-center">
          <CircleCheck size={40} strokeWidth={1.5} className="mx-auto text-success-600" aria-hidden />
          <h1 className="display mt-3 text-3xl md:text-4xl">Grup randevun hazır</h1>
          <p className="muted mt-2">Diğer kişilere WhatsApp ile bilgi gönderildi.</p>
        </div>

        <ul className="space-y-2">
          {created.appointments.map((a) => (
            <li key={a.appointmentId} className="card flex items-start justify-between gap-3">
              <div>
                <p className="font-medium">{a.forCustomer.firstName}</p>
                <p className="muted">
                  {formatDateTr(a.date)} · {timeLabel(a.startMin)}–{timeLabel(a.endMin)}
                </p>
                <p className="muted">Usta: {a.staffName}</p>
              </div>
              <span className="font-semibold tabular-nums">{formatTl(a.totalPrice)}</span>
            </li>
          ))}
        </ul>

        <div className="flex items-baseline justify-between border-t border-sand-200 pt-3">
          <span className="muted">Toplam</span>
          <span className="text-lg font-semibold tabular-nums">{formatTl(created.totalPrice)}</span>
        </div>

        <div className="flex flex-col gap-2 sm:flex-row">
          <Link href="/randevularim" className="btn-primary flex-1 text-center">
            Randevularımı gör
          </Link>
          <Link href="/" className="btn-secondary flex-1 text-center">
            Ana sayfa
          </Link>
        </div>
      </section>
    );
  }

  const summaryOf = (p: Person) => {
    const list = p.serviceIds.map((id) => serviceById.get(id)).filter((s): s is Service => !!s);
    return {
      list,
      min: list.reduce((n, s) => n + serviceTotalMin(s), 0),
      price: list.reduce((n, s) => n + s.price, 0),
    };
  };
  const personName = (p: Person, i: number) =>
    includeSelf && i === 0 ? customer.firstName : p.firstName.trim();
  const grandPrice = people.reduce((n, p) => n + summaryOf(p).price, 0);

  return (
    <div className="page-shell space-y-6 pt-6 pb-4">
      <Stepper
        step={step}
        onJump={(s) => {
          if (s >= step) return;
          if (step === 4) void releaseLock();
          setError(null);
          setWarning(null);
          setStep(s);
        }}
      />

      {warning && (
        <div className="alert alert-warning" role="alert">
          <TriangleAlert size={16} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
          <p>{warning}</p>
        </div>
      )}
      {error && (
        <div className="alert alert-danger" role="alert">
          <TriangleAlert size={16} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
          <p>{error}</p>
        </div>
      )}

      {/* ---------- 1) Kişiler ---------- */}
      {step === 1 && (
        <section className="space-y-4">
          <div>
            <p className="eyebrow">Grup randevusu</p>
            <h1 className="display text-3xl md:text-4xl">Kimler geliyor?</h1>
            <p className="muted mt-2">
              Herkes aynı saatte, ayrı ustalarla başlar. Diğer kişilere WhatsApp ile bilgi gönderilir.
            </p>
          </div>

          {/* Kişi sayısı: büyük −/+ ve tek dokunuşla 2·3·4 seçimi */}
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-[4px] border border-plum-600/30 bg-plum-50/60 p-4">
            <div>
              <p className="eyebrow">Kaç kişi?</p>
              <p className="muted mt-0.5 text-xs">
                {MIN_PEOPLE}–{MAX_PEOPLE} kişi seçebilirsin
              </p>
            </div>
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setPeopleCount(people.length - 1)}
                disabled={people.length <= MIN_PEOPLE}
                aria-label="Bir kişi azalt"
                className="grid h-12 w-12 place-items-center rounded-full border border-ink-900/20 bg-white text-ink-900 transition-colors hover:border-plum-600 hover:text-plum-600 disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:border-ink-900/20 disabled:hover:text-ink-900"
              >
                <Minus size={20} strokeWidth={1.75} aria-hidden />
              </button>
              <p className="min-w-[4.5rem] text-center" aria-live="polite">
                <span className="display block text-4xl leading-none tabular-nums">{people.length}</span>
                <span className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-500">kişi</span>
              </p>
              <button
                type="button"
                onClick={() => setPeopleCount(people.length + 1)}
                disabled={people.length >= MAX_PEOPLE}
                aria-label="Bir kişi ekle"
                className="grid h-12 w-12 place-items-center rounded-full bg-plum-600 text-white transition-colors hover:bg-plum-700 disabled:cursor-not-allowed disabled:opacity-35"
              >
                <Plus size={20} strokeWidth={1.75} aria-hidden />
              </button>
            </div>
            <div className="flex w-full gap-2" role="group" aria-label="Kişi sayısını seç">
              {Array.from({ length: MAX_PEOPLE - MIN_PEOPLE + 1 }, (_, k) => MIN_PEOPLE + k).map((n) => (
                <button
                  key={n}
                  type="button"
                  onClick={() => setPeopleCount(n)}
                  aria-pressed={people.length === n}
                  className="chip flex-1 justify-center"
                >
                  {n} kişi
                </button>
              ))}
            </div>
          </div>

          <ul className="space-y-3">
            {people.map((p, i) => {
              const isSelf = includeSelf && i === 0;
              const err = personError(p, i);
              const touched = p.firstName !== '' || p.phone !== '';
              return (
                <li key={p.key} className="card space-y-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="eyebrow">{i + 1}. kişi</p>
                    {people.length > MIN_PEOPLE && i > 0 && (
                      <button
                        type="button"
                        className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-sand-300 px-3 text-xs font-semibold uppercase tracking-[0.1em] text-ink-700 transition-colors hover:border-danger-700 hover:text-danger-700"
                        onClick={() => removePerson(i)}
                        aria-label={`${i + 1}. kişiyi çıkar`}
                      >
                        <X size={14} strokeWidth={1.75} aria-hidden /> Çıkar
                      </button>
                    )}
                  </div>

                  {i === 0 && (
                    <label className="flex items-start gap-3 text-sm text-ink-700">
                      <input
                        type="checkbox"
                        className="mt-0.5 h-5 w-5 shrink-0 rounded-[2px] accent-plum-600"
                        checked={includeSelf}
                        onChange={(e) => toggleSelf(e.target.checked)}
                      />
                      <span>Ben de katılıyorum</span>
                    </label>
                  )}

                  {isSelf ? (
                    <div className="space-y-1">
                      <p className="font-medium">{customer.firstName}</p>
                      <p className="muted">0{selfPhone}</p>
                    </div>
                  ) : (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div>
                        <label className="label" htmlFor={`g-name-${p.key}`}>
                          Ad
                        </label>
                        <input
                          id={`g-name-${p.key}`}
                          className="field"
                          value={p.firstName}
                          onChange={(e) => updatePerson(i, { firstName: e.target.value })}
                          maxLength={40}
                          autoComplete="off"
                          placeholder="Ayşe"
                        />
                      </div>
                      <div>
                        <label className="label" htmlFor={`g-phone-${p.key}`}>
                          Telefon
                        </label>
                        <input
                          id={`g-phone-${p.key}`}
                          className="field"
                          value={p.phone}
                          onChange={(e) => updatePerson(i, { phone: e.target.value })}
                          inputMode="tel"
                          autoComplete="off"
                          placeholder="0532 000 00 00"
                        />
                      </div>
                    </div>
                  )}
                  {!isSelf && touched && err && (
                    <p className="text-sm text-danger-700" role="status">
                      {err}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>

          {people.length < MAX_PEOPLE ? (
            <button
              type="button"
              onClick={addPerson}
              className="group flex w-full items-center justify-center gap-3 rounded-[4px] border-2 border-dashed border-plum-600/40 bg-white/60 px-4 py-5 text-plum-600 transition-colors hover:border-plum-600 hover:bg-plum-50"
            >
              <span className="grid h-10 w-10 place-items-center rounded-full bg-plum-600 text-white transition-transform group-hover:scale-105">
                <UserPlus size={18} strokeWidth={1.75} aria-hidden />
              </span>
              <span className="text-left">
                <span className="block font-semibold">Kişi ekle</span>
                <span className="block text-xs text-ink-500">
                  {people.length}/{MAX_PEOPLE} kişi · {MAX_PEOPLE - people.length} kişi daha eklenebilir
                </span>
              </span>
            </button>
          ) : (
            <p className="rounded-[4px] border border-sand-200 px-4 py-3 text-center text-sm text-ink-500">
              En fazla {MAX_PEOPLE} kişi ekleyebilirsin. Daha kalabalık gruplar için salonu ara.
            </p>
          )}
        </section>
      )}

      {/* ---------- 2) Hizmetler ---------- */}
      {step === 2 && (
        <section className="space-y-5">
          <div>
            <h1 className="display text-3xl md:text-4xl">Kim ne yaptıracak?</h1>
            <p className="muted mt-2">Her kişi için hizmet seç; istersen usta tercihi belirt.</p>
          </div>
          {people.map((p, i) => (
            <PersonServices
              key={p.key}
              index={i}
              name={personName(p, i) || `${i + 1}. kişi`}
              person={p}
              categories={categories}
              services={services}
              summary={summaryOf(p)}
              onChange={(patch) => updatePerson(i, patch)}
            />
          ))}
        </section>
      )}

      {/* ---------- 3) Ortak saat ---------- */}
      {step === 3 && (
        <section className="space-y-4">
          <div>
            <h1 className="display text-3xl md:text-4xl">Ortak saat</h1>
            <p className="muted mt-2">Hepiniz aynı saatte başlarsınız; her kişiye ayrı usta atanır.</p>
          </div>

          <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1" role="group" aria-label="Tarih seç">
            {Array.from({ length: DAY_WINDOW }, (_, i) => dateKey(i)).map((key) => {
              const { weekday, day } = dayChipLabel(key);
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setDate(key)}
                  aria-pressed={date === key}
                  className={`chip touch-target h-auto shrink-0 flex-col gap-0 px-3 py-2 ${date === key ? 'chip-active' : ''}`}
                >
                  <span className="text-[11px] uppercase">{weekday}</span>
                  <span className="font-semibold tabular-nums">{day}</span>
                </button>
              );
            })}
          </div>

          <p className="muted">{formatDateTr(date)}</p>

          {loadingAvail && <p className="muted">Ortak saatler aranıyor…</p>}

          {availability && availability.options.length > 0 && (
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-4" role="group" aria-label="Ortak saatler">
              {availability.options.map((o) => {
                const active = chosenStart === o.startMin;
                return (
                  <button
                    key={o.startMin}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setChosenStart(o.startMin)}
                    className={`chip chip-primary touch-target ${active ? 'chip-active' : ''}`}
                  >
                    <span className="font-semibold tabular-nums">{timeLabel(o.startMin)}</span>
                  </button>
                );
              })}
            </div>
          )}

          {availability && availability.options.length === 0 && (
            <div className="space-y-3">
              <div className="alert alert-warning">
                <TriangleAlert size={16} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
                <p>Bu gün için hepiniz aynı saatte başlayamıyorsunuz.</p>
              </div>
              {availability.suggestDates.length > 0 && (
                <div>
                  <p className="label">Şu günler uygun olabilir</p>
                  <div className="flex flex-wrap gap-2">
                    {availability.suggestDates.map((s) => (
                      <button key={s.date} type="button" className="chip" onClick={() => setDate(s.date)}>
                        {formatDateTr(s.date)}{' '}
                        <span className="text-ink-500">({s.optionCount} saat)</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <Link href="/randevu" className="btn-link">
                Ayrı ayrı randevu al
              </Link>
            </div>
          )}

          {chosenOption && <PersonBreakdown people={people} option={chosenOption} nameOf={personName} />}
        </section>
      )}

      {/* ---------- 4) Onay ---------- */}
      {step === 4 && lock && (
        <section className="space-y-5">
          <NameEditor firstName={customer.firstName} />
          <CountdownBar secondsLeft={secondsLeft} onCancel={goBack} />

          <div className="space-y-1">
            <p className="eyebrow">Özet</p>
            <p className="font-medium">
              {formatDateTr(date)} · {chosenOption ? timeLabel(chosenOption.startMin) : ''}
            </p>
          </div>

          <ul className="space-y-3">
            {people.map((p, i) => {
              const a = chosenOption?.assignments.find((x) => x.personIndex === i);
              const l = lock.locks.find((x) => x.personIndex === i);
              const sum = summaryOf(p);
              const start = a?.startMin ?? l?.startMin ?? 0;
              const end = a?.endMin ?? l?.endMin ?? 0;
              return (
                <li key={p.key} className="card space-y-2">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium">{personName(p, i)}</p>
                      <p className="muted">{sum.list.map((s) => s.name).join(', ')}</p>
                      <p className="muted">
                        Usta: {a?.staffName ?? '—'} · {timeLabel(start)}–{timeLabel(end)}
                      </p>
                    </div>
                    <span className="font-semibold tabular-nums">
                      {formatTl(a?.totalPrice ?? l?.totalPrice ?? sum.price)}
                    </span>
                  </div>
                  <div>
                    <label className="label" htmlFor={`g-note-${p.key}`}>
                      Not (isteğe bağlı)
                    </label>
                    <input
                      id={`g-note-${p.key}`}
                      className="field"
                      value={p.notes}
                      maxLength={300}
                      onChange={(e) => updatePerson(i, { notes: e.target.value })}
                    />
                  </div>
                </li>
              );
            })}
          </ul>

          <div className="flex items-baseline justify-between border-t border-sand-200 pt-3">
            <span className="muted">Toplam</span>
            <span className="text-lg font-semibold tabular-nums">
              {formatTl(lock.locks.reduce((n, l) => n + l.totalPrice, 0))}
            </span>
          </div>
        </section>
      )}

      {/* ---------- Alt eylem çubuğu ---------- */}
      <div className="sticky bottom-20 z-10 md:bottom-4">
        <div className="rounded-[4px] border border-sand-200 bg-white p-3">
          <div className="mb-2 flex items-center justify-between text-sm">
            <span className="muted">{people.length} kişi</span>
            <span className="font-semibold tabular-nums">{formatTl(grandPrice)}</span>
          </div>
          <div className="flex gap-2">
            {step > 1 && (
              <button type="button" className="btn-secondary flex-1" disabled={busy} onClick={goBack}>
                Geri
              </button>
            )}
            {step === 1 && (
              <button
                type="button"
                className="btn-primary flex-1"
                disabled={!step1Valid}
                onClick={() => setStep(2)}
              >
                Devam
              </button>
            )}
            {step === 2 && (
              <button
                type="button"
                className="btn-primary flex-1"
                disabled={!step2Valid}
                onClick={() => setStep(3)}
              >
                Saatleri gör
              </button>
            )}
            {step === 3 && (
              <button
                type="button"
                className="btn-primary flex-1"
                disabled={!chosenOption || busy}
                onClick={() => void acquireLock()}
              >
                {busy ? 'Saatler tutuluyor…' : 'Devam'}
              </button>
            )}
            {step === 4 && (
              <button
                type="button"
                className="btn-primary flex-1"
                disabled={busy || !lock}
                onClick={() => void confirm()}
              >
                {busy ? 'Oluşturuluyor…' : 'Randevuları oluştur'}
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
                  state === 'current' ? 'text-ink-900' : state === 'done' ? 'text-plum-600' : 'text-ink-400'
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

function CountdownBar({ secondsLeft, onCancel }: { secondsLeft: number; onCancel: () => void }) {
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
        Saatler grubunuz için tutuldu ·{' '}
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

function PersonBreakdown({
  people,
  option,
  nameOf,
}: {
  people: Person[];
  option: GroupOption;
  nameOf: (p: Person, i: number) => string;
}) {
  return (
    <div className="card space-y-2">
      <p className="eyebrow">Seçilen saat · {timeLabel(option.startMin)}</p>
      <ul className="space-y-2">
        {option.assignments.map((a) => {
          const p = people[a.personIndex];
          if (!p) return null;
          return (
            <li key={a.personIndex} className="flex items-start justify-between gap-3 text-sm">
              <div>
                <p className="font-medium">{nameOf(p, a.personIndex) || `${a.personIndex + 1}. kişi`}</p>
                <p className="muted">
                  {a.staffName} · {timeLabel(a.startMin)}–{timeLabel(a.endMin)} · {durationLabel(a.totalMin)}
                </p>
              </div>
              <span className="font-semibold tabular-nums">{formatTl(a.totalPrice)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function PersonServices({
  index,
  name,
  person,
  categories,
  services,
  summary,
  onChange,
}: {
  index: number;
  name: string;
  person: Person;
  categories: Category[];
  services: Service[];
  summary: { list: Service[]; min: number; price: number };
  onChange: (patch: Partial<Person>) => void;
}) {
  const [activeCategory, setActiveCategory] = useState<number | null>(categories[0]?.id ?? null);
  const [staff, setStaff] = useState<{ id: number; name: string }[]>([]);

  function toggle(id: number) {
    const next = person.serviceIds.includes(id)
      ? person.serviceIds.filter((x) => x !== id)
      : [...person.serviceIds, id];
    onChange({ serviceIds: next });
  }

  const idsKey = person.serviceIds.join(',');
  useEffect(() => {
    if (idsKey === '') {
      setStaff([]);
      return;
    }
    let cancelled = false;
    fetch(`/api/catalog/staff?serviceIds=${idsKey}`, { cache: 'no-store' })
      .then((r) => r.json())
      .then((body) => {
        if (cancelled || !body.ok) return;
        const list = body.data.staff as { id: number; name: string }[];
        setStaff(list);
        // Seçili usta artık tüm hizmetleri yapamıyorsa "fark etmez"e dön.
        if (person.staffId !== null && !list.some((s) => s.id === person.staffId)) {
          onChange({ staffId: null });
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idsKey]);

  return (
    <div className="card space-y-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="font-medium">
          {index + 1}. {name}
        </p>
        <span className="muted tabular-nums">
          {summary.list.length === 0
            ? 'Hizmet seçilmedi'
            : `${durationLabel(summary.min)} · ${formatTl(summary.price)}`}
        </span>
      </div>

      <div
        className="-mx-1 flex gap-2 overflow-x-auto px-1 pb-1"
        role="group"
        aria-label={`${name} için kategori`}
      >
        {categories.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => setActiveCategory(c.id)}
            aria-pressed={activeCategory === c.id}
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
            const selected = person.serviceIds.includes(service.id);
            return (
              <li key={service.id}>
                <button
                  type="button"
                  onClick={() => toggle(service.id)}
                  aria-pressed={selected}
                  className={`w-full rounded-[4px] border p-3 text-left transition-colors ${
                    selected ? 'border-plum-600 bg-plum-50' : 'border-sand-200 bg-white hover:border-ink-300'
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium">{service.name}</p>
                      <span className="badge mt-1.5 bg-sand-100 text-ink-700">
                        {durationLabel(serviceTotalMin(service))}
                      </span>
                    </div>
                    <span className="shrink-0 font-semibold tabular-nums">{formatTl(service.price)}</span>
                  </div>
                </button>
              </li>
            );
          })}
      </ul>

      {person.serviceIds.length > 0 && staff.length > 0 && (
        <div>
          <p className="label">Usta tercihi</p>
          <div className="flex flex-wrap gap-2" role="group" aria-label={`${name} için usta tercihi`}>
            <button
              type="button"
              aria-pressed={person.staffId === null}
              onClick={() => onChange({ staffId: null })}
              className={`chip ${person.staffId === null ? 'chip-active' : ''}`}
            >
              Fark etmez
            </button>
            {staff.map((s) => (
              <button
                key={s.id}
                type="button"
                aria-pressed={person.staffId === s.id}
                onClick={() => onChange({ staffId: s.id })}
                className={`chip ${person.staffId === s.id ? 'chip-active' : ''}`}
              >
                {s.name}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
