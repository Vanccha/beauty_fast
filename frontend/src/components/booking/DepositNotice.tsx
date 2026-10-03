'use client';

import { Check, Copy, Info } from 'lucide-react';
import { useState } from 'react';

import { formatTl } from '@/lib/api-client';
import { DEPOSIT_POLICY } from '@/lib/appointment-status';

/** Müşteriye dönen kapora bilgisi (backend `deposit.customer_view`). */
export interface CustomerDeposit {
  /** AWAITING | PAID | REFUND_DUE | REFUNDED | FORFEITED | NONE */
  status: string;
  amount: number | null;
  policy: string;
  refundDueAt?: string | null;
  /** Yalnızca bekleyen kaporada ve yalnızca randevuyu alana: */
  payAmount?: number;
  iban?: string;
  accountName?: string;
  bankName?: string;
  reference?: string;
}

function CopyButton({ value, label }: { value: string; label: string }) {
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setDone(true);
      window.setTimeout(() => setDone(false), 2000);
    } catch {
      /* pano erişimi yoksa kullanıcı metni elle seçer */
    }
  }
  return (
    <button
      type="button"
      className="btn-ghost btn-sm inline-flex items-center gap-1 !px-2 !py-1 text-xs"
      aria-label={`${label} kopyala`}
      onClick={() => void copy()}
    >
      {done ? <Check size={14} strokeWidth={1.5} aria-hidden /> : <Copy size={14} strokeWidth={1.5} aria-hidden />}
      {done ? 'Kopyalandı' : 'Kopyala'}
    </button>
  );
}

/**
 * Kapora kutusu: bekleyen kaporada tutar + IBAN (kopyala) + alıcı + açıklama +
 * politika; diğer durumlarda kısa bilgi. Randevu henüz KESİNLEŞMEMİŞTİR.
 */
export function DepositNotice({ deposit, compact = false }: { deposit: CustomerDeposit; compact?: boolean }) {
  if (deposit.status === 'AWAITING') {
    const amount = deposit.payAmount ?? deposit.amount ?? 0;
    return (
      <div className="space-y-3 rounded-2xl border border-brass-300 bg-brass-300/15 p-4" role="status">
        <div>
          <p className="text-sm font-semibold text-brass-700">Kapora bekleniyor</p>
          <p className="mt-0.5 text-sm text-ink-700">
            Randevunuzun kesinleşmesi için <strong className="tabular-nums">{formatTl(amount)}</strong> kapora
            gerekiyor. Havale ulaştığında randevunuz onaylanır ve size WhatsApp ile bilgi verilir.
          </p>
        </div>
        {deposit.iban ? (
          <dl className="space-y-2 text-sm">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <dt className="muted text-xs">IBAN</dt>
                <dd className="break-all font-mono font-medium">{deposit.iban}</dd>
              </div>
              <CopyButton value={deposit.iban.replace(/\s+/g, '')} label="IBAN" />
            </div>
            <div>
              <dt className="muted text-xs">Alıcı</dt>
              <dd className="font-medium">
                {deposit.accountName}
                {deposit.bankName ? ` · ${deposit.bankName}` : ''}
              </dd>
            </div>
            {deposit.reference && (
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="min-w-0">
                  <dt className="muted text-xs">Açıklama (havale açıklamasına yazın)</dt>
                  <dd className="font-medium">{deposit.reference}</dd>
                </div>
                <CopyButton value={deposit.reference} label="Açıklama" />
              </div>
            )}
          </dl>
        ) : (
          <p className="muted text-sm">Ödeme bilgileri randevuyu alan kişiye WhatsApp ile gönderildi.</p>
        )}
        {!compact && (
          <p className="flex items-start gap-1.5 text-xs text-ink-700">
            <Info size={14} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
            {deposit.policy || DEPOSIT_POLICY}
          </p>
        )}
      </div>
    );
  }

  if (deposit.status === 'PAID') {
    return (
      <p className="badge bg-success-50 text-success-700">
        Kapora ödendi{deposit.amount ? ` · ${formatTl(deposit.amount)}` : ''}
      </p>
    );
  }
  if (deposit.status === 'REFUND_DUE') {
    return (
      <p className="rounded-xl bg-sand-100 px-3 py-2 text-sm text-ink-700">
        Kaporanız 48 saat içinde tarafınıza gönderilecektir.
      </p>
    );
  }
  if (deposit.status === 'REFUNDED') {
    return <p className="badge bg-sand-100 text-ink-500">Kapora iade edildi</p>;
  }
  if (deposit.status === 'FORFEITED') {
    return <p className="badge bg-danger-50 text-danger-700">Kapora iade edilmedi</p>;
  }
  return null;
}
