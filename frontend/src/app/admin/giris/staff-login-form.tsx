'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ApiError, apiSend } from '@/lib/api-client';

export function StaffLoginForm() {
  const router = useRouter();
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiSend('/api/auth/staff/login', 'POST', { phone, password });
      router.push('/admin');
      router.refresh();
    } catch (e) {
      // Sunucu "telefon mu şifre mi yanlış" ayrımını yapmaz; mesaj olduğu gibi gösterilir.
      setError(e instanceof ApiError ? e.message : 'Giriş yapılamadı.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card space-y-4 !p-5">
      <div>
        <label className="label" htmlFor="phone">
          Telefon
        </label>
        <input
          id="phone"
          className="field"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          inputMode="tel"
          autoComplete="username"
          placeholder="0555 111 00 01"
          autoFocus
          required
        />
      </div>

      <div>
        <label className="label" htmlFor="password">
          Şifre
        </label>
        <input
          id="password"
          type="password"
          className="field"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
        />
      </div>

      {error && <p className="text-sm text-danger-700" role="alert">{error}</p>}

      <button className="btn-primary w-full" disabled={busy}>
        {busy ? 'Giriş yapılıyor…' : 'Giriş yap'}
      </button>
    </form>
  );
}
