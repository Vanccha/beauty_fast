'use client';

import { Pencil } from 'lucide-react';
import { useState } from 'react';

import { ApiError, apiSend } from '@/lib/api-client';

export interface DepositSettingsData {
  enabled: boolean;
  percent: number;
  minAmount: number;
  /** 4'lü gruplanmış IBAN. */
  iban: string;
  accountName: string;
  bankName: string;
  deadlineMinutes: number;
  /** Kaydedilmiş özel metin; null ise varsayılan kullanılıyor. */
  message: string | null;
  defaultMessage: string;
  placeholders: Record<string, string>;
  maxLength: number;
  policy: string;
  /** Örnek verilerle doldurulmuş hali — müşteriye giden metin. */
  preview: string;
}

/**
 * Kapora: açıkken online randevu "Kapora bekleniyor" olarak oluşur ve müşteriye
 * IBAN'lı WhatsApp mesajı gider; havale ulaşınca yönetici "Kapora ödendi" der.
 * Sistem para taşımaz, yalnızca izler ve hatırlatır (kurallar backend'de:
 * `services/deposit.py`). Yalnızca yönetici ve salon sahibi görür.
 */
export function DepositSettings({ initial }: { initial: DepositSettingsData }) {
  const [data, setData] = useState(initial);
  const [enabled, setEnabled] = useState(initial.enabled);
  const [percent, setPercent] = useState(String(initial.percent));
  const [minAmount, setMinAmount] = useState(String(initial.minAmount));
  const [iban, setIban] = useState(initial.iban);
  const [accountName, setAccountName] = useState(initial.accountName);
  const [bankName, setBankName] = useState(initial.bankName);
  const [deadline, setDeadline] = useState(String(initial.deadlineMinutes));
  const [message, setMessage] = useState(initial.message ?? initial.defaultMessage);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [editing, setEditing] = useState(false);
  const textareaId = 'deposit-message';

  const percentNum = Number.parseInt(percent, 10);
  const minNum = Number.parseInt(minAmount, 10);
  const deadlineNum = Number.parseInt(deadline, 10);
  const valid =
    Number.isInteger(percentNum) &&
    percentNum >= 1 &&
    percentNum <= 100 &&
    Number.isInteger(minNum) &&
    minNum >= 0 &&
    Number.isInteger(deadlineNum) &&
    deadlineNum >= 5 &&
    deadlineNum <= 1440;
  const dirty =
    enabled !== data.enabled ||
    percentNum !== data.percent ||
    minNum !== data.minAmount ||
    iban.replace(/\s+/g, '').toUpperCase() !== data.iban.replace(/\s+/g, '') ||
    accountName !== data.accountName ||
    bankName !== data.bankName ||
    deadlineNum !== data.deadlineMinutes ||
    message !== (data.message ?? data.defaultMessage);

  function reset(from: DepositSettingsData) {
    setEnabled(from.enabled);
    setPercent(String(from.percent));
    setMinAmount(String(from.minAmount));
    setIban(from.iban);
    setAccountName(from.accountName);
    setBankName(from.bankName);
    setDeadline(String(from.deadlineMinutes));
    setMessage(from.message ?? from.defaultMessage);
  }

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const next = await apiSend<DepositSettingsData>('/api/admin/settings/deposit', 'PUT', {
        enabled,
        percent: percentNum,
        minAmount: minNum,
        iban: iban.trim(),
        accountName: accountName.trim(),
        bankName: bankName.trim(),
        deadlineMinutes: deadlineNum,
        message,
      });
      setData(next);
      reset(next);
      setSaved(true);
      setEditing(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Kaydedilemedi.');
    } finally {
      setBusy(false);
    }
  }

  function cancel() {
    reset(data);
    setError(null);
    setSaved(false);
    setEditing(false);
  }

  function insert(token: string) {
    const el = document.getElementById(textareaId) as HTMLTextAreaElement | null;
    if (!el) {
      setMessage((m) => m + token);
      return;
    }
    const start = el.selectionStart ?? message.length;
    const end = el.selectionEnd ?? message.length;
    setMessage(message.slice(0, start) + token + message.slice(end));
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + token.length, start + token.length);
    });
  }

  if (!editing) {
    return (
      <section className="card space-y-2 !p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="eyebrow">Kapora</h2>
            <span className={`badge ${data.enabled ? 'bg-success-50 text-success-700' : 'bg-sand-100 text-ink-500'}`}>
              {data.enabled ? `Açık · %${data.percent}, en az ${data.minAmount} TL` : 'Kapalı'}
            </span>
          </div>
          <button
            type="button"
            className="btn-secondary btn-sm inline-flex items-center gap-1.5"
            onClick={() => {
              setSaved(false);
              setEditing(true);
            }}
          >
            <Pencil size={14} strokeWidth={1.5} aria-hidden />
            Düzenle
          </button>
        </div>
        {data.enabled ? (
          <p className="muted text-sm">
            {data.accountName} · {data.iban}
            {data.bankName ? ` · ${data.bankName}` : ''}
          </p>
        ) : (
          <p className="muted text-sm">
            Kapalıyken randevular eskisi gibi doğrudan onaylanır. Açınca online randevular kapora
            ödenene kadar “Kapora bekleniyor” olarak kalır.
          </p>
        )}
        {saved && <p className="text-sm text-success-700">Kaydedildi.</p>}
      </section>
    );
  }

  return (
    <section className="card space-y-3 !p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="eyebrow">Kapora</h2>
          <p className="muted mt-1 text-xs">
            Kapora = en az alt sınır, en çok randevu tutarı olmak üzere tutarın yüzdesi (tam TL).
            Havale ulaşınca takvimden <strong>Kapora ödendi</strong> diyerek randevuyu onaylarsınız.
          </p>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm font-medium">
          <input
            type="checkbox"
            className="h-4 w-4 accent-plum-600"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          {enabled ? 'Açık' : 'Kapalı'}
        </label>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div>
          <label className="label" htmlFor="deposit-percent">
            Oran (%)
          </label>
          <input
            id="deposit-percent"
            type="number"
            inputMode="numeric"
            min={1}
            max={100}
            className="field"
            value={percent}
            onChange={(e) => setPercent(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="deposit-min">
            Alt sınır (TL)
          </label>
          <input
            id="deposit-min"
            type="number"
            inputMode="numeric"
            min={0}
            className="field"
            value={minAmount}
            onChange={(e) => setMinAmount(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="deposit-deadline">
            Gecikme uyarısı (dk)
          </label>
          <input
            id="deposit-deadline"
            type="number"
            inputMode="numeric"
            min={5}
            max={1440}
            className="field"
            value={deadline}
            onChange={(e) => setDeadline(e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className="label" htmlFor="deposit-iban">
            IBAN
          </label>
          <input
            id="deposit-iban"
            className="field font-mono"
            placeholder="TR00 0000 0000 0000 0000 0000 00"
            autoComplete="off"
            value={iban}
            onChange={(e) => setIban(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="deposit-account">
            Hesap sahibi
          </label>
          <input
            id="deposit-account"
            className="field"
            maxLength={120}
            value={accountName}
            onChange={(e) => setAccountName(e.target.value)}
          />
        </div>
        <div>
          <label className="label" htmlFor="deposit-bank">
            Banka (isteğe bağlı)
          </label>
          <input
            id="deposit-bank"
            className="field"
            maxLength={80}
            value={bankName}
            onChange={(e) => setBankName(e.target.value)}
          />
        </div>
      </div>

      <div>
        <label className="label" htmlFor={textareaId}>
          WhatsApp mesajı
        </label>
        <textarea
          id={textareaId}
          className="field min-h-40"
          maxLength={data.maxLength}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {Object.entries(data.placeholders).map(([key, label]) => (
            <button
              key={key}
              type="button"
              className="btn-ghost btn-sm !px-2.5 !py-1 text-xs"
              title={label}
              onClick={() => insert(key)}
            >
              {key}
            </button>
          ))}
          <span className="ml-auto text-xs tabular-nums text-ink-500">
            {message.length}/{data.maxLength}
          </span>
        </div>
        <p className="muted mt-1 text-xs">
          Boş kalan bir değerin (ör. {'{banka}'}) geçtiği satır mesajdan çıkarılır.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className="btn-primary btn-sm" disabled={busy || !dirty || !valid} onClick={save}>
          Kaydet
        </button>
        {message !== data.defaultMessage && (
          <button type="button" className="btn-ghost btn-sm" disabled={busy} onClick={() => setMessage(data.defaultMessage)}>
            Varsayılan metne dön
          </button>
        )}
        <button type="button" className="btn-ghost btn-sm" disabled={busy} onClick={cancel}>
          Vazgeç
        </button>
        {error && <span className="text-sm text-danger-700">{error}</span>}
      </div>

      <div>
        <p className="label">Müşteriye giden mesaj (kayıtlı hali, örnek verilerle)</p>
        <p className="whitespace-pre-wrap rounded-[2px] border border-sand-200 bg-sand-50 px-3 py-2 text-sm text-ink-900">
          {data.preview}
        </p>
      </div>
      <p className="muted text-xs">Müşteriye gösterilen politika: {data.policy}</p>
    </section>
  );
}
