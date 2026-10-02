'use client';

import { ArrowLeft, TriangleAlert } from 'lucide-react';
import Link from 'next/link';
import { useEffect, useState } from 'react';

import { PhoneInput } from '@/components/auth/PhoneInput';
import { ApiError, apiSend } from '@/lib/api-client';
import { formatPhone, isValidMobile, normalizePhone } from '@/lib/phone';

export interface VerifiedCustomer {
  id: number;
  firstName: string;
  lastName: string | null;
  phone: string;
  tier: string;
  loyaltyPoints: number;
  engagementOptIn: boolean;
}

interface SendResult {
  phone: string;
  expiresAt: string;
  devCode?: string;
}

const PLACEHOLDER_NAME = 'Yeni Üye';
const RESEND_SECONDS = 45;

/**
 * Telefon → WhatsApp kodu → (yalnızca yeni numaraysa) ad adımı.
 *
 * Kod önce adsız doğrulanır; kod tüketildiği için ad, oturum açıldıktan
 * sonra `PATCH /api/me` ile kaydedilir. Telefonda gerçek bir ad zaten
 * kayıtlıysa ad ASLA tekrar sorulmaz.
 *
 * `devCode` yalnızca geliştirmede döner; varsa kutuya otomatik yazılır.
 *
 * KVKK: aydınlatma metni bağlantısı numara girilirken gösterilir. Ticari
 * ileti onayı AYRI, İSTEĞE BAĞLI ve varsayılan işaretsizdir.
 */
export function PhoneVerify({
  onVerified,
  title,
  description,
  compact = false,
}: {
  onVerified: (customer: VerifiedCustomer) => void;
  title?: string;
  description?: string;
  compact?: boolean;
}) {
  const [step, setStep] = useState<'phone' | 'code' | 'name'>('phone');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [firstName, setFirstName] = useState('');
  const [marketingConsent, setMarketingConsent] = useState(false);
  const [sent, setSent] = useState<SendResult | null>(null);
  const [verified, setVerified] = useState<VerifiedCustomer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(0);
  const [resendLeft, setResendLeft] = useState(0);

  // Kodun kalan geçerlilik süresi
  useEffect(() => {
    if (!sent) return;
    const tick = () => {
      setSecondsLeft(
        Math.max(0, Math.floor((new Date(sent.expiresAt).getTime() - Date.now()) / 1000)),
      );
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [sent]);

  // Yeniden gönder geri sayımı
  useEffect(() => {
    if (resendLeft <= 0) return;
    const id = setTimeout(() => setResendLeft((s) => s - 1), 1000);
    return () => clearTimeout(id);
  }, [resendLeft]);

  async function sendCode() {
    setError(null);
    setBusy(true);
    try {
      const result = await apiSend<SendResult>('/api/auth/otp/send', 'POST', { phone });
      setSent(result);
      setCode(result.devCode ?? '');
      setResendLeft(RESEND_SECONDS);
      setStep('code');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Kod gönderilemedi.');
    } finally {
      setBusy(false);
    }
  }

  async function handleSend(event: React.FormEvent) {
    event.preventDefault();
    await sendCode();
  }

  async function handleVerify(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await apiSend<{ isNewCustomer: boolean; customer: VerifiedCustomer }>(
        '/api/auth/otp/verify',
        'POST',
        { phone, code, marketingConsent },
      );
      setVerified(result.customer);
      if (result.isNewCustomer || result.customer.firstName === PLACEHOLDER_NAME) {
        setStep('name');
      } else {
        onVerified(result.customer);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Doğrulama başarısız.');
    } finally {
      setBusy(false);
    }
  }

  async function handleName(event: React.FormEvent) {
    event.preventDefault();
    if (!verified) return;
    setError(null);
    setBusy(true);
    try {
      const updated = await apiSend<VerifiedCustomer>('/api/me', 'PATCH', {
        firstName: firstName.trim(),
      });
      onVerified({ ...verified, ...updated });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Ad kaydedilemedi.');
    } finally {
      setBusy(false);
    }
  }

  const errorBox = error && (
    <div className="alert alert-danger" role="alert">
      <TriangleAlert size={16} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
      <p>{error}</p>
    </div>
  );

  const header = (title || description) && (
    <div className={compact ? '' : 'text-center'}>
      {title && <h1 className={compact ? 'display text-xl' : 'display text-4xl'}>{title}</h1>}
      {description && <p className="muted mt-2">{description}</p>}
    </div>
  );

  const wrap = (children: React.ReactNode) => (
    <div className={compact ? 'space-y-4' : 'mx-auto w-full max-w-md space-y-6'}>
      {header}
      {children}
    </div>
  );

  if (step === 'name') {
    return wrap(
      <form onSubmit={handleName} className={compact ? 'space-y-4' : 'card space-y-5'}>
        <p className="muted">Numaran doğrulandı. Sana nasıl hitap edelim?</p>
        <div>
          <label className="label" htmlFor="pv-firstName">
            Adın
          </label>
          <input
            id="pv-firstName"
            className="field"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            placeholder="Ayşe"
            maxLength={40}
            autoComplete="given-name"
            autoFocus
            required
          />
        </div>
        {errorBox}
        <button className="btn-primary w-full" disabled={busy || firstName.trim().length < 1}>
          Devam et
        </button>
      </form>,
    );
  }

  if (step === 'code') {
    return wrap(
      <form onSubmit={handleVerify} className={compact ? 'space-y-4' : 'card space-y-5'}>
        <p className="muted">
          <strong>{formatPhone(sent?.phone)}</strong> numarasına WhatsApp üzerinden gönderilen 6 haneli kodu gir.
        </p>

        <div>
          <label className="label" htmlFor="pv-code">
            Doğrulama kodu
          </label>
          <input
            id="pv-code"
            className="field text-center text-2xl tabular-nums tracking-[0.4em]"
            value={code}
            onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
            inputMode="numeric"
            autoComplete="one-time-code"
            placeholder="······"
            autoFocus
            required
          />
        </div>

        {sent?.devCode && (
          <p className="alert alert-warning text-xs">
            Geliştirme modu: kod <strong>{sent.devCode}</strong> (sunucu log&apos;una da yazıldı).
          </p>
        )}

        {errorBox}

        <button className="btn-primary w-full" disabled={busy || code.length < 4}>
          Doğrula
        </button>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            className="btn-link"
            onClick={() => {
              setStep('phone');
              setError(null);
            }}
          >
            <ArrowLeft size={16} strokeWidth={1.5} aria-hidden />
            Numarayı değiştir
          </button>
          <span className="muted tabular-nums">
            {secondsLeft > 0
              ? `Kod ${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, '0')} geçerli`
              : 'Kodun süresi doldu'}
          </span>
        </div>

        <button
          type="button"
          className="btn-link"
          disabled={busy || resendLeft > 0}
          onClick={() => void sendCode()}
        >
          {resendLeft > 0 ? `Kodu tekrar gönder (${resendLeft} sn)` : 'Kodu tekrar gönder'}
        </button>
      </form>,
    );
  }

  return wrap(
    <form onSubmit={handleSend} className={compact ? 'space-y-4' : 'card space-y-5'}>
      <div>
        <label className="label" htmlFor="pv-phone">
          Cep telefonu
        </label>
        <PhoneInput id="pv-phone" onChange={setPhone} autoFocus={!compact} required />
        <p className="mt-1 text-xs text-ink-500">Yurtdışı numara için ülke kodunu seç.</p>
      </div>

      <label className="flex items-start gap-3 text-sm text-ink-700">
        <input
          type="checkbox"
          className="mt-0.5 h-5 w-5 shrink-0 rounded-[2px] accent-plum-600"
          checked={marketingConsent}
          onChange={(e) => setMarketingConsent(e.target.checked)}
        />
        <span>
          Bakım zamanı hatırlatmaları ve kampanyalar için WhatsApp ile ileti almak istiyorum.{' '}
          <span className="text-ink-500">
            (İsteğe bağlı ·{' '}
            <Link href="/acik-riza#ticari-ileti" target="_blank" className="underline underline-offset-2">
              Onay metni
            </Link>
            )
          </span>
        </span>
      </label>

      {errorBox}

      <button className="btn-primary w-full" disabled={busy || !isValidMobile(normalizePhone(phone))}>
        Kod gönder
      </button>

      <p className="text-xs leading-relaxed text-ink-500">
        Telefon numaran ve adın işlenir; doğrulama kodu WhatsApp ile gönderilir. Ayrıntılar:{' '}
        <Link href="/kvkk" target="_blank" className="underline">
          KVKK Aydınlatma Metni
        </Link>
        .
      </p>
    </form>,
  );
}
