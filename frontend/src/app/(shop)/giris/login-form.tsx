'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { ApiError, apiSend } from '@/lib/api-client';

interface SendResult {
  phone: string;
  expiresAt: string;
  devCode?: string;
}

/**
 * Telefon + OTP giriş akışı.
 *
 * `devCode` yalnızca geliştirmede döner (`NODE_ENV !== 'production'`);
 * varsa kutuya otomatik yazılır ki demo sırasında konsola bakmaya gerek
 * kalmasın.
 */
export function LoginForm({ nextUrl }: { nextUrl: string }) {
  const router = useRouter();

  const [step, setStep] = useState<'phone' | 'code'>('phone');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [firstName, setFirstName] = useState('');
  const [needsName, setNeedsName] = useState(false);
  const [sent, setSent] = useState<SendResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [secondsLeft, setSecondsLeft] = useState(0);

  // Kodun kalan geçerlilik süresi
  useEffect(() => {
    if (!sent) return;
    const tick = () => {
      const remaining = Math.max(
        0,
        Math.floor((new Date(sent.expiresAt).getTime() - Date.now()) / 1000),
      );
      setSecondsLeft(remaining);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [sent]);

  async function handleSend(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await apiSend<SendResult>('/api/auth/otp/send', 'POST', { phone });
      setSent(result);
      setCode(result.devCode ?? '');
      setStep('code');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Kod gönderilemedi.');
    } finally {
      setBusy(false);
    }
  }

  async function handleVerify(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const result = await apiSend<{ isNewCustomer: boolean }>('/api/auth/otp/verify', 'POST', {
        phone,
        code,
        firstName: firstName || undefined,
      });

      // Yeni üye adını girmediyse önce adını iste, sonra devam et.
      if (result.isNewCustomer && !firstName) {
        setNeedsName(true);
        return;
      }
      router.push(nextUrl);
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Doğrulama başarısız.');
    } finally {
      setBusy(false);
    }
  }

  async function handleName(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await apiSend('/api/auth/otp/verify', 'POST', { phone, code, firstName });
      router.push(nextUrl);
      router.refresh();
    } catch {
      // Kod tüketilmişse profil adı sonradan hesap sayfasından girilebilir.
      router.push(nextUrl);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  if (needsName) {
    return (
      <form onSubmit={handleName} className="card space-y-3">
        <div>
          <label className="label" htmlFor="firstName">
            Adın
          </label>
          <input
            id="firstName"
            className="field"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            placeholder="Ayşe"
            autoFocus
            required
          />
        </div>
        <button className="btn-primary w-full" disabled={busy}>
          Devam et
        </button>
      </form>
    );
  }

  if (step === 'code') {
    return (
      <form onSubmit={handleVerify} className="card space-y-3">
        <p className="muted">
          <strong>0{sent?.phone}</strong> numarasına WhatsApp üzerinden gönderilen 6 haneli kodu gir.
        </p>

        <div>
          <label className="label" htmlFor="code">
            Doğrulama kodu
          </label>
          <input
            id="code"
            className="field text-center text-2xl tracking-[0.4em]"
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
          <p className="rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800">
            Geliştirme modu: kod <strong>{sent.devCode}</strong> (sunucu log'una da
            yazıldı).
          </p>
        )}

        {error && <p className="text-sm text-rose-600">{error}</p>}

        <button className="btn-primary w-full" disabled={busy || code.length < 4}>
          Giriş yap
        </button>

        <div className="flex items-center justify-between">
          <button
            type="button"
            className="btn-ghost px-0 text-sm"
            onClick={() => {
              setStep('phone');
              setError(null);
            }}
          >
            ← Numarayı değiştir
          </button>
          <span className="muted tabular-nums">
            {secondsLeft > 0
              ? `Kod ${Math.floor(secondsLeft / 60)}:${String(secondsLeft % 60).padStart(2, '0')} geçerli`
              : 'Kodun süresi doldu'}
          </span>
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={handleSend} className="card space-y-3">
      <div>
        <label className="label" htmlFor="phone">
          Cep telefonu
        </label>
        <input
          id="phone"
          className="field"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          inputMode="tel"
          autoComplete="tel"
          placeholder="0532 000 00 00"
          autoFocus
          required
        />
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <button className="btn-primary w-full" disabled={busy || phone.replace(/\D/g, '').length < 10}>
        Kod gönder
      </button>
    </form>
  );
}
