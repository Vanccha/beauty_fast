'use client';

import { TriangleAlert } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ApiError, apiSend } from '@/lib/api-client';

/** "Merhaba, {ad}" + satır içi ad değiştirme (PATCH /api/me). */
export function NameEditor({ firstName }: { firstName: string }) {
  const router = useRouter();
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(firstName);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await apiSend('/api/me', 'PATCH', { firstName: value.trim() });
      setEditing(false);
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Ad kaydedilemedi.');
    } finally {
      setBusy(false);
    }
  }

  if (!editing) {
    return (
      <div>
        <h1 className="display text-3xl md:text-4xl">Merhaba, {firstName}</h1>
        <button
          type="button"
          className="btn-link mt-2"
          onClick={() => {
            setValue(firstName);
            setEditing(true);
          }}
        >
          İsmimi değiştir
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={save} className="max-w-sm space-y-3">
      <div>
        <label className="label" htmlFor="ne-firstName">
          Adın
        </label>
        <input
          id="ne-firstName"
          className="field"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          maxLength={40}
          autoComplete="given-name"
          autoFocus
          required
        />
      </div>
      {error && (
        <div className="alert alert-danger" role="alert">
          <TriangleAlert size={16} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
          <p>{error}</p>
        </div>
      )}
      <div className="flex gap-2">
        <button type="button" className="btn-secondary btn-sm" onClick={() => setEditing(false)}>
          Vazgeç
        </button>
        <button className="btn-primary btn-sm" disabled={busy || value.trim().length < 1}>
          {busy ? 'Kaydediliyor…' : 'Kaydet'}
        </button>
      </div>
    </form>
  );
}
