'use client';

import { AtSign, Plus } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { PhoneInput } from '@/components/auth/PhoneInput';
import { ApiError, apiGet, apiSend, formatTl, timeLabel } from '@/lib/api-client';
import { formatPhone, isValidMobile, normalizePhone } from '@/lib/phone';

export interface StaffRow {
  id: number;
  name: string;
  phone: string;
  role: string;
  photoUrl: string | null;
  instagram: string | null;
  commissionPercent: number;
  isActive: boolean;
  serviceIds: number[];
  earnings: { count: number; revenue: number; commission: number };
}

interface ServiceCategory {
  id: number;
  name: string;
  services: { id: number; name: string }[];
}

interface EarningsDetail {
  count: number;
  revenue: number;
  commission: number;
  commissionPercent: number;
  appointments: { id: number; date: string; startMin: number; services: string[]; price: number; commission: number }[];
}

const ROLE_LABEL: Record<string, string> = { OWNER: 'Salon sahibi', MANAGER: 'Yönetici', STAFF: 'Personel' };

function dateTr(key: string): string {
  const [y, m, d] = key.split('-');
  return `${d}.${m}.${y}`;
}

/** Düzenlenebilir mi? Yönetici yalnızca "Personel" rolündekileri yönetir. */
function canManage(viewerRole: string, row: StaffRow): boolean {
  return viewerRole === 'OWNER' || row.role === 'STAFF';
}

export function StaffManager({
  staff,
  services,
  viewerRole,
  viewerId,
  from,
  to,
}: {
  staff: StaffRow[];
  services: ServiceCategory[];
  viewerRole: string;
  viewerId: number;
  from: string;
  to: string;
}) {
  const [editing, setEditing] = useState<number | 'new' | null>(null);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="eyebrow">Ekip ({staff.length})</h2>
        {editing !== 'new' && (
          <button type="button" className="btn-primary btn-sm" onClick={() => setEditing('new')}>
            <Plus size={14} strokeWidth={1.75} aria-hidden /> Personel ekle
          </button>
        )}
      </div>

      {editing === 'new' && (
        <StaffForm
          key="new"
          services={services}
          viewerRole={viewerRole}
          onDone={() => setEditing(null)}
        />
      )}

      <ul className="space-y-2">
        {staff.map((row) => (
          <li key={row.id}>
            {editing === row.id ? (
              <StaffForm
                key={`edit-${row.id}`}
                row={row}
                services={services}
                viewerRole={viewerRole}
                onDone={() => setEditing(null)}
              />
            ) : (
              <StaffCard
                row={row}
                from={from}
                to={to}
                manageable={canManage(viewerRole, row)}
                isSelf={row.id === viewerId}
                onEdit={() => setEditing(row.id)}
              />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ */

function StaffCard({
  row,
  from,
  to,
  manageable,
  isSelf,
  onEdit,
}: {
  row: StaffRow;
  from: string;
  to: string;
  manageable: boolean;
  isSelf: boolean;
  onEdit: () => void;
}) {
  const router = useRouter();
  const [detail, setDetail] = useState<EarningsDetail | null>(null);
  const [open, setOpen] = useState(false);
  const [confirm, setConfirm] = useState<'delete' | 'deactivate' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggleDetail() {
    if (open) return setOpen(false);
    setOpen(true);
    setError(null);
    try {
      setDetail(await apiGet<EarningsDetail>(`/api/admin/staff/${row.id}?from=${from}&to=${to}`));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Kazanç dökümü alınamadı.');
    }
  }

  async function run(action: () => Promise<unknown>, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setConfirm(null);
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  const setActive = (isActive: boolean) =>
    run(() => apiSend(`/api/admin/staff/${row.id}`, 'PATCH', { isActive }), 'Güncellenemedi.');
  const remove = () => run(() => apiSend(`/api/admin/staff/${row.id}`, 'DELETE'), 'Silinemedi.');

  return (
    <article className={`card space-y-3 !p-3 md:!p-4 ${row.isActive ? '' : 'opacity-70'}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          {row.photoUrl ? (
            <img src={row.photoUrl} alt="" className="h-12 w-12 shrink-0 rounded-full object-cover" />
          ) : (
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-plum-50 text-lg font-semibold text-plum-700">
              {row.name.charAt(0)}
            </span>
          )}
          <div className="min-w-0">
            <p className="font-semibold">
              {row.name}
              <span className="badge ml-2 align-middle">{ROLE_LABEL[row.role] ?? row.role}</span>
              {!row.isActive && <span className="badge ml-1 align-middle !bg-danger-50 !text-danger-700">Pasif</span>}
            </p>
            <p className="muted text-sm tabular-nums">{formatPhone(row.phone)}</p>
            {row.instagram && (
              <a
                href={`https://instagram.com/${row.instagram}`}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-sm text-plum-600 hover:underline"
              >
                <AtSign size={14} strokeWidth={1.5} aria-hidden /> @{row.instagram}
              </a>
            )}
          </div>
        </div>

        <dl className="grid grid-cols-3 gap-4 text-right">
          <div>
            <dt className="muted text-xs">Randevu</dt>
            <dd className="font-semibold tabular-nums">{row.earnings.count}</dd>
          </div>
          <div>
            <dt className="muted text-xs">Ciro</dt>
            <dd className="font-semibold tabular-nums">{formatTl(row.earnings.revenue)}</dd>
          </div>
          <div>
            <dt className="muted text-xs">Pay (%{row.commissionPercent})</dt>
            <dd className="font-semibold tabular-nums text-plum-700">{formatTl(row.earnings.commission)}</dd>
          </div>
        </dl>
      </div>

      {error && <p className="rounded-xl bg-danger-50 px-3 py-2 text-sm text-danger-700">{error}</p>}

      {!confirm && (
        <div className="flex flex-wrap gap-1.5">
          <button type="button" className="btn-secondary btn-sm" onClick={() => void toggleDetail()}>
            {open ? 'Dökümü gizle' : 'Kazanç dökümü'}
          </button>
          {manageable && (
            <>
              <button type="button" className="btn-secondary btn-sm" onClick={onEdit}>
                Düzenle
              </button>
              {!isSelf && row.role !== 'OWNER' && (
                <>
                  {row.isActive ? (
                    <button type="button" className="btn-ghost btn-sm" disabled={busy} onClick={() => setConfirm('deactivate')}>
                      Pasife al
                    </button>
                  ) : (
                    <button type="button" className="btn-ghost btn-sm" disabled={busy} onClick={() => void setActive(true)}>
                      Aktifleştir
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-sm border border-rose-300 bg-white text-rose-700 hover:bg-sand-100"
                    disabled={busy}
                    onClick={() => setConfirm('delete')}
                  >
                    Sil
                  </button>
                </>
              )}
            </>
          )}
        </div>
      )}

      {confirm && (
        <div className="space-y-2 rounded-xl border border-sand-300 bg-white px-3 py-2.5">
          <p className="text-sm">
            {confirm === 'delete'
              ? `${row.name} kalıcı olarak silinsin mi? Bu işlem geri alınamaz. Randevu geçmişi olan personel silinemez; onu pasife alabilirsiniz.`
              : `${row.name} pasife alınsın mı? Girişi kapanır ve yeni randevu alamaz; geçmiş kayıtları korunur.`}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              className={confirm === 'delete' ? 'btn-danger btn-sm' : 'btn-primary btn-sm'}
              disabled={busy}
              onClick={() => void (confirm === 'delete' ? remove() : setActive(false))}
            >
              {confirm === 'delete' ? 'Evet, sil' : 'Evet, pasife al'}
            </button>
            <button type="button" className="btn-ghost btn-sm" disabled={busy} onClick={() => setConfirm(null)}>
              Vazgeç
            </button>
          </div>
        </div>
      )}

      {open && (
        <div className="rounded-xl bg-sand-100 p-3">
          {!detail && !error && <p className="muted text-sm">Yükleniyor…</p>}
          {detail && detail.appointments.length === 0 && (
            <p className="muted text-sm">Bu dönemde tamamlanan randevu yok.</p>
          )}
          {detail && detail.appointments.length > 0 && (
            <ul className="divide-y divide-sand-200 text-sm">
              {detail.appointments.map((a) => (
                <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-1.5">
                  <span className="min-w-0">
                    <span className="tabular-nums text-ink-500">
                      {dateTr(a.date)} {timeLabel(a.startMin)}
                    </span>{' '}
                    {a.services.join(' + ')}
                  </span>
                  <span className="tabular-nums">
                    {formatTl(a.price)} <span className="text-plum-700">→ {formatTl(a.commission)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}

/* ------------------------------------------------------------------ */

function StaffForm({
  row,
  services,
  viewerRole,
  onDone,
}: {
  row?: StaffRow;
  services: ServiceCategory[];
  viewerRole: string;
  onDone: () => void;
}) {
  const router = useRouter();
  const isNew = !row;
  const [name, setName] = useState(row?.name ?? '');
  const [phone, setPhone] = useState(row?.phone ?? '');
  const [instagram, setInstagram] = useState(row?.instagram ?? '');
  const [commission, setCommission] = useState(String(row?.commissionPercent ?? 0));
  const [password, setPassword] = useState('');
  const [role, setRole] = useState(row?.role ?? 'STAFF');
  const [serviceIds, setServiceIds] = useState<number[]>(row?.serviceIds ?? []);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pct = Number(commission);
  const pctValid = commission.trim() !== '' && Number.isFinite(pct) && pct >= 0 && pct <= 100;
  const phoneOk = isValidMobile(normalizePhone(phone));
  const passwordOk = isNew ? password.length >= 8 : password === '' || password.length >= 8;
  const valid = name.trim().length >= 2 && phoneOk && pctValid && passwordOk;

  const toggleService = (id: number) =>
    setServiceIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (!valid) return;
    setBusy(true);
    setError(null);
    try {
      const common = { name: name.trim(), phone, instagram: instagram.trim() || null, commissionPercent: pct, serviceIds };
      if (isNew) {
        await apiSend('/api/admin/staff', 'POST', { ...common, password, role });
      } else {
        await apiSend(`/api/admin/staff/${row.id}`, 'PATCH', {
          ...common,
          ...(password ? { password } : {}),
          ...(viewerRole === 'OWNER' && row.role !== 'OWNER' ? { role } : {}),
        });
      }
      onDone();
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Kaydedilemedi.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-4 border-plum-300 !p-4">
      <h3 className="display text-lg">{isNew ? 'Yeni personel' : `${row.name} — düzenle`}</h3>

      <div className="grid gap-3 md:grid-cols-2">
        <div>
          <label className="label" htmlFor="sf-name">
            Ad soyad
          </label>
          <input id="sf-name" className="field" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="label" htmlFor="sf-phone">
            Telefon (giriş numarası)
          </label>
          <PhoneInput id="sf-phone" defaultValue={row?.phone ?? ''} onChange={setPhone} />
          {phone && !phoneOk && <p className="mt-1 text-xs text-danger-700">Geçerli bir cep telefonu girin.</p>}
        </div>
        <div>
          <label className="label" htmlFor="sf-ig">
            Instagram
          </label>
          <input
            id="sf-ig"
            className="field"
            value={instagram}
            placeholder="kullanici_adi veya profil bağlantısı"
            onChange={(e) => setInstagram(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="sf-pct">
            Kazanç yüzdesi (%)
          </label>
          <input
            id="sf-pct"
            className="field"
            inputMode="decimal"
            value={commission}
            onChange={(e) => setCommission(e.target.value.replace(',', '.'))}
          />
          <p className="muted mt-1 text-xs">Tamamlanan randevu cirosundan personele ayrılan pay. 0–100.</p>
        </div>
        <div>
          <label className="label" htmlFor="sf-pass">
            {isNew ? 'Şifre' : 'Yeni şifre'}
          </label>
          <input
            id="sf-pass"
            type="password"
            autoComplete="new-password"
            className="field"
            value={password}
            placeholder={isNew ? 'En az 8 karakter' : 'Değiştirmek istemiyorsanız boş bırakın'}
            onChange={(e) => setPassword(e.target.value)}
          />
          {password && password.length < 8 && <p className="mt-1 text-xs text-danger-700">En az 8 karakter olmalı.</p>}
          {!isNew && password && (
            <p className="muted mt-1 text-xs">Şifre değişince personelin açık oturumları kapanır.</p>
          )}
        </div>
        {viewerRole === 'OWNER' && row?.role !== 'OWNER' && (
          <div>
            <label className="label" htmlFor="sf-role">
              Rol
            </label>
            <select id="sf-role" className="field" value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="STAFF">Personel</option>
              <option value="MANAGER">Yönetici</option>
            </select>
          </div>
        )}
      </div>

      <fieldset>
        <legend className="label">Yaptığı hizmetler</legend>
        <p className="muted mb-2 text-xs">Hiç hizmet seçilmezse personel müşteri randevularında görünmez.</p>
        <div className="space-y-2">
          {services.map((group) => (
            <div key={group.id}>
              <p className="text-xs font-semibold text-ink-500">{group.name}</p>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1">
                {group.services.map((s) => (
                  <label key={s.id} className="flex items-center gap-1.5 text-sm">
                    <input type="checkbox" checked={serviceIds.includes(s.id)} onChange={() => toggleService(s.id)} />
                    {s.name}
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
      </fieldset>

      {error && <p className="rounded-xl bg-danger-50 px-3 py-2 text-sm text-danger-700">{error}</p>}

      <div className="flex gap-2">
        <button type="submit" className="btn-primary btn-sm" disabled={busy || !valid}>
          {busy ? 'Kaydediliyor…' : isNew ? 'Personel ekle' : 'Kaydet'}
        </button>
        <button type="button" className="btn-ghost btn-sm" disabled={busy} onClick={onDone}>
          Vazgeç
        </button>
      </div>
    </form>
  );
}
