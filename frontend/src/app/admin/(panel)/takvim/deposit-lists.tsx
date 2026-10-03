'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ApiError, apiSend, formatTl } from '@/lib/api-client';
import { refundRemainingLabel, spanLabel, type DepositLists, type DepositRow } from '@/lib/deposit';
import { formatPhone } from '@/lib/phone';

type Pending = { kind: 'PAID' | 'CANCEL' | 'REFUND'; id: number } | null;

/**
 * Takvimin üstünde: "Kapora bekleyenler" ve "İade bekleyenler" (yalnızca
 * yönetici/sahip). Gecikenler vurgulanır. İşlemler satır içi onayla yapılır.
 */
export function DepositListsPanel({ lists }: { lists: DepositLists }) {
  const router = useRouter();
  const [pending, setPending] = useState<Pending>(null);
  const [notifyRefund, setNotifyRefund] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (lists.awaiting.length === 0 && lists.refunds.length === 0) return null;

  async function run(action: () => Promise<unknown>, fallback: string) {
    setBusy(true);
    setError(null);
    try {
      await action();
      setPending(null);
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : fallback);
    } finally {
      setBusy(false);
    }
  }

  const markPaid = (row: DepositRow) =>
    run(() => apiSend(`/api/admin/appointments/${row.id}/deposit/paid`, 'POST', { expectedVersion: row.version }), 'İşaretlenemedi.');
  const cancelUnpaid = (row: DepositRow) =>
    run(
      () =>
        apiSend(`/api/admin/appointments/${row.id}/status`, 'PATCH', {
          status: 'CANCELLED',
          expectedVersion: row.version,
          notifyCustomer: true,
          reason: 'DEPOSIT_UNPAID',
        }),
      'İptal edilemedi.',
    );
  const markRefunded = (row: DepositRow) =>
    run(
      () =>
        apiSend(`/api/admin/appointments/${row.id}/deposit/refunded`, 'POST', {
          expectedVersion: row.version,
          notifyCustomer: notifyRefund,
        }),
      'İşaretlenemedi.',
    );

  return (
    <div className="space-y-3">
      {error && (
        <p className="rounded-[4px] border border-brass-300 bg-sand-100 px-3 py-2 text-sm text-ink-900">{error}</p>
      )}

      {lists.awaiting.length > 0 && (
        <section className="card space-y-2 !p-4" aria-label="Kapora bekleyenler">
          <div className="flex items-center justify-between gap-2">
            <h2 className="eyebrow">Kapora bekleyenler ({lists.awaiting.length})</h2>
            <span className="muted text-xs">{lists.deadlineMinutes} dk sonra gecikmiş sayılır</span>
          </div>
          <ul className="divide-y divide-sand-200">
            {lists.awaiting.map((row) => {
              const open = pending?.id === row.id ? pending.kind : null;
              return (
                <li
                  key={row.id}
                  className={`space-y-2 py-2.5 ${row.overdue ? '-mx-2 rounded-xl bg-danger-50/60 px-2' : ''}`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold">
                        {row.customer.name}
                        <span className="ml-2 text-sm font-normal tabular-nums text-ink-500">
                          {row.dateLabel} {row.startLabel}
                        </span>
                      </p>
                      <p className="muted text-sm">{row.services.join(' + ')}</p>
                      <p className="muted text-xs tabular-nums">
                        {row.payer && row.payer.id !== row.customer.id
                          ? `Ödeyecek: ${row.payer.name} · ${formatPhone(row.payer.phone)}`
                          : formatPhone(row.customer.phone)}
                        {row.reference && ` · Açıklama: ${row.reference}`}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold tabular-nums">{formatTl(row.amount ?? 0)}</p>
                      {row.groupSize && row.groupSize > 1 && (
                        <p className="muted text-xs">
                          Grup · {row.groupSize} kişi · toplam {formatTl(row.groupAmount ?? 0)}
                        </p>
                      )}
                      <p className={`text-xs tabular-nums ${row.overdue ? 'font-semibold text-danger-700' : 'text-ink-500'}`}>
                        {row.overdue ? 'Gecikti · ' : ''}
                        {spanLabel(row.ageMinutes ?? 0)} önce istendi
                      </p>
                    </div>
                  </div>

                  {!open && (
                    <div className="flex flex-wrap gap-1.5">
                      <button
                        type="button"
                        className="btn-primary btn-sm"
                        disabled={busy}
                        onClick={() => setPending({ kind: 'PAID', id: row.id })}
                      >
                        Kapora ödendi
                      </button>
                      <button
                        type="button"
                        className="btn btn-sm border border-rose-300 bg-white text-rose-700 hover:bg-sand-100"
                        disabled={busy}
                        onClick={() => setPending({ kind: 'CANCEL', id: row.id })}
                      >
                        İptal et
                      </button>
                    </div>
                  )}
                  {open === 'PAID' && (
                    <div className="space-y-2 rounded-xl border border-sand-300 bg-white px-3 py-2.5">
                      <p className="text-sm">
                        {formatTl(row.groupAmount ?? row.amount ?? 0)} kapora hesabınıza ulaştı mı? Randevu onaylanır ve
                        müşteriye bilgi mesajı gider.
                      </p>
                      <div className="flex gap-2">
                        <button type="button" className="btn-primary btn-sm" disabled={busy} onClick={() => void markPaid(row)}>
                          Evet, ulaştı
                        </button>
                        <button type="button" className="btn-ghost btn-sm" onClick={() => setPending(null)}>
                          Vazgeç
                        </button>
                      </div>
                    </div>
                  )}
                  {open === 'CANCEL' && (
                    <div className="space-y-2 rounded-xl border border-rose-300 bg-white px-3 py-2.5">
                      <p className="text-sm">
                        Randevu “Kapora yatırılmadı” nedeniyle iptal edilir; müşteriye bilgi mesajı gider.
                      </p>
                      <div className="flex gap-2">
                        <button type="button" className="btn-danger btn-sm" disabled={busy} onClick={() => void cancelUnpaid(row)}>
                          Evet, iptal et
                        </button>
                        <button type="button" className="btn-ghost btn-sm" onClick={() => setPending(null)}>
                          Vazgeç
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {lists.refunds.length > 0 && (
        <section className="card space-y-2 !p-4" aria-label="İade bekleyenler">
          <h2 className="eyebrow">İade bekleyenler ({lists.refunds.length})</h2>
          <ul className="divide-y divide-sand-200">
            {lists.refunds.map((row) => {
              const open = pending?.id === row.id ? pending.kind : null;
              const remaining = row.remainingMinutes ?? 0;
              return (
                <li
                  key={row.id}
                  className={`space-y-2 py-2.5 ${row.overdue ? '-mx-2 rounded-xl bg-danger-50/60 px-2' : ''}`}
                >
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-semibold">
                        {row.payer?.name ?? row.customer.name}
                        <span className="ml-2 text-sm font-normal tabular-nums text-ink-500">
                          {row.dateLabel} {row.startLabel} randevusu
                        </span>
                      </p>
                      <p className="muted text-xs tabular-nums">
                        {formatPhone(row.payer?.phone ?? row.customer.phone)}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold tabular-nums">{formatTl(row.amount ?? 0)}</p>
                      <p className={`text-xs tabular-nums ${row.overdue ? 'font-semibold text-danger-700' : 'text-ink-500'}`}>
                        İade süresi: {refundRemainingLabel(remaining)}
                      </p>
                    </div>
                  </div>
                  {!open && (
                    <button
                      type="button"
                      className="btn-primary btn-sm"
                      disabled={busy}
                      onClick={() => setPending({ kind: 'REFUND', id: row.id })}
                    >
                      Kapora iade edildi
                    </button>
                  )}
                  {open === 'REFUND' && (
                    <div className="space-y-2 rounded-xl border border-sand-300 bg-white px-3 py-2.5">
                      <p className="text-sm">{formatTl(row.amount ?? 0)} müşteriye iade edildi olarak işaretlensin mi?</p>
                      <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={notifyRefund} onChange={(e) => setNotifyRefund(e.target.checked)} />
                        Müşteriye “Kaporanız iade edilmiştir” mesajı gönder
                      </label>
                      <div className="flex gap-2">
                        <button type="button" className="btn-primary btn-sm" disabled={busy} onClick={() => void markRefunded(row)}>
                          Evet, iade edildi
                        </button>
                        <button type="button" className="btn-ghost btn-sm" onClick={() => setPending(null)}>
                          Vazgeç
                        </button>
                      </div>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
