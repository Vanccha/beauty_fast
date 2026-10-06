'use client';

import { useRouter } from 'next/navigation';
import { useState } from 'react';

function iso(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

/** Kazanç dönemi: hazır kısayollar + özel tarih aralığı (URL'de `from`/`to`). */
export function PeriodForm({ from, to }: { from: string; to: string }) {
  const router = useRouter();
  const [start, setStart] = useState(from);
  const [end, setEnd] = useState(to);

  const go = (a: string, b: string) => router.push(`/admin/personel?from=${a}&to=${b}`);

  function thisMonth() {
    const n = new Date();
    go(iso(new Date(n.getFullYear(), n.getMonth(), 1)), iso(n));
  }
  function lastMonth() {
    const n = new Date();
    go(iso(new Date(n.getFullYear(), n.getMonth() - 1, 1)), iso(new Date(n.getFullYear(), n.getMonth(), 0)));
  }
  function last30() {
    const n = new Date();
    go(iso(new Date(n.getFullYear(), n.getMonth(), n.getDate() - 29)), iso(n));
  }

  return (
    <form
      className="card flex flex-wrap items-end gap-3 !p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (start && end && start <= end) go(start, end);
      }}
    >
      <div>
        <label className="label" htmlFor="p-from">
          Başlangıç
        </label>
        <input id="p-from" type="date" className="field" value={start} onChange={(e) => setStart(e.target.value)} />
      </div>
      <div>
        <label className="label" htmlFor="p-to">
          Bitiş
        </label>
        <input id="p-to" type="date" className="field" value={end} onChange={(e) => setEnd(e.target.value)} />
      </div>
      <button type="submit" className="btn-primary btn-sm" disabled={!start || !end || start > end}>
        Göster
      </button>
      <div className="flex flex-wrap gap-1.5">
        <button type="button" className="btn-secondary btn-sm" onClick={thisMonth}>
          Bu ay
        </button>
        <button type="button" className="btn-secondary btn-sm" onClick={lastMonth}>
          Geçen ay
        </button>
        <button type="button" className="btn-secondary btn-sm" onClick={last30}>
          Son 30 gün
        </button>
      </div>
    </form>
  );
}
