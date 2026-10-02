'use client';

import { Trash2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ApiError, apiSend, apiUpload } from '@/lib/api-client';

interface Item {
  id: number;
  title: string;
  imageUrl: string;
  categoryName: string | null;
  staffName: string | null;
}

export function PortfolioManager({
  items,
  categories,
  staff,
}: {
  items: Item[];
  categories: { id: number; name: string }[];
  staff: { id: number; name: string }[];
}) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [staffId, setStaffId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(event: React.FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('file', file);
      form.append('title', title);
      if (description) form.append('description', description);
      if (categoryId) form.append('categoryId', categoryId);
      if (staffId) form.append('staffId', staffId);

      await apiUpload('/api/admin/portfolio', form);
      setFile(null);
      setTitle('');
      setDescription('');
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Yükleme başarısız.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form onSubmit={upload} className="card grid grid-cols-1 gap-2 !p-3 md:grid-cols-2">
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="field"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <input
          className="field"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Başlık (örn. Balyaj — Küllü Kumral)"
          required
        />
        <select className="field" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">Kategori seç</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
        <select className="field" value={staffId} onChange={(e) => setStaffId(e.target.value)}>
          <option value="">Usta (varsayılan: sen)</option>
          {staff.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <input
          className="field md:col-span-2"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Açıklama (isteğe bağlı)"
        />
        {error && <p className="text-sm text-danger-700 md:col-span-2">{error}</p>}
        <button className="btn-primary btn-sm md:col-span-2" disabled={busy || !file || !title}>
          {busy ? 'Yükleniyor…' : 'Galeriye ekle'}
        </button>
      </form>

      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        {items.map((item) => (
          <figure key={item.id} className="overflow-hidden rounded-[4px] border border-sand-200 bg-white">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={item.imageUrl}
              alt={item.title}
              loading="lazy"
              className="aspect-square w-full object-cover"
            />
            <figcaption className="space-y-0.5 p-2">
              <p className="truncate text-sm font-medium text-ink-900">{item.title}</p>
              <p className="muted truncate text-xs">
                {item.categoryName ?? '—'}
                {item.staffName ? ` · ${item.staffName}` : ''}
              </p>
              <button
                type="button"
                className="btn-ghost btn-sm w-full text-rose-700"
                onClick={async () => {
                  await apiSend(`/api/admin/portfolio?id=${item.id}`, 'DELETE').catch(() => undefined);
                  router.refresh();
                }}
              >
                <Trash2 size={14} strokeWidth={1.5} aria-hidden /> Kaldır
              </button>
            </figcaption>
          </figure>
        ))}
      </div>
    </>
  );
}
