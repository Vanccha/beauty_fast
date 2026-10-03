'use client';

import { ArrowDown, ArrowUp, Eye, EyeOff, ImagePlus, Pencil, Trash2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { ApiError, apiSend, apiUpload } from '@/lib/api-client';

interface Item {
  id: number;
  title: string;
  imageUrl: string;
  description: string | null;
  isPublished: boolean;
  categoryId: number | null;
  staffId: number | null;
  categoryName: string | null;
  staffName: string | null;
}

interface Option {
  id: number;
  name: string;
}

export function PortfolioManager({
  items: initialItems,
  categories,
  staff,
}: {
  items: Item[];
  categories: Option[];
  staff: Option[];
}) {
  const router = useRouter();
  const [items, setItems] = useState(initialItems);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setItems(initialItems), [initialItems]);

  function fail(e: unknown, fallback: string) {
    setError(e instanceof ApiError ? e.message : fallback);
  }

  async function togglePublished(item: Item) {
    setBusyId(item.id);
    setError(null);
    try {
      const form = new FormData();
      form.append('isPublished', String(!item.isPublished));
      await apiUpload(`/api/admin/portfolio/${item.id}`, form, 'PATCH');
      router.refresh();
    } catch (e) {
      fail(e, 'Durum güncellenemedi.');
    } finally {
      setBusyId(null);
    }
  }

  async function remove(item: Item) {
    setBusyId(item.id);
    setError(null);
    try {
      await apiSend(`/api/admin/portfolio?id=${item.id}`, 'DELETE');
      setConfirmId(null);
      router.refresh();
    } catch (e) {
      fail(e, 'Silinemedi.');
    } finally {
      setBusyId(null);
    }
  }

  async function move(index: number, delta: -1 | 1) {
    const target = index + delta;
    if (target < 0 || target >= items.length) return;
    const next = [...items];
    [next[index], next[target]] = [next[target], next[index]];
    setItems(next); // iyimser güncelleme
    setError(null);
    try {
      await apiSend('/api/admin/portfolio/reorder', 'POST', { ids: next.map((i) => i.id) });
      router.refresh();
    } catch (e) {
      setItems(items);
      fail(e, 'Sıralama kaydedilemedi.');
    }
  }

  return (
    <>
      <UploadForm categories={categories} staff={staff} />

      {error && (
        <p role="alert" className="text-sm text-danger-700">
          {error}
        </p>
      )}

      {items.length === 0 ? (
        <p className="muted text-sm">Henüz galeride iş yok. Yukarıdan ilk görseli ekleyin.</p>
      ) : (
        <ul className="grid grid-cols-2 gap-2 md:grid-cols-4">
          {items.map((item, index) => {
            const editing = editingId === item.id;
            const confirming = confirmId === item.id;
            const busy = busyId === item.id;
            return (
              <li
                key={item.id}
                className={`card flex flex-col overflow-hidden !p-0 ${editing ? 'col-span-2 md:col-span-4' : ''}`}
              >
                <div className="relative">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={item.imageUrl}
                    alt={item.title}
                    loading="lazy"
                    className={`aspect-square w-full object-cover transition-opacity ${
                      item.isPublished ? '' : 'opacity-45'
                    } ${editing ? 'max-h-56 md:max-h-64' : ''}`}
                  />
                  {!item.isPublished && (
                    <span className="chip absolute left-2 top-2 bg-white/90">Gizli</span>
                  )}
                  <span className="chip absolute right-2 top-2 bg-white/90 tabular-nums">
                    {index + 1}
                  </span>
                </div>

                <div className="space-y-1.5 p-2">
                  <p className="truncate text-sm font-medium text-ink-900">{item.title}</p>
                  <p className="muted truncate text-xs">
                    {item.categoryName ?? '—'}
                    {item.staffName ? ` · ${item.staffName}` : ''}
                  </p>

                  {editing ? (
                    <EditPanel
                      item={item}
                      categories={categories}
                      staff={staff}
                      onClose={() => setEditingId(null)}
                      onSaved={() => {
                        setEditingId(null);
                        router.refresh();
                      }}
                    />
                  ) : confirming ? (
                    <div className="space-y-1.5 rounded-xl bg-rose-50 p-2">
                      <p className="text-xs text-rose-700">Bu iş kalıcı olarak silinsin mi?</p>
                      <div className="flex gap-1">
                        <button
                          type="button"
                          className="btn-secondary btn-sm flex-1"
                          onClick={() => setConfirmId(null)}
                          disabled={busy}
                        >
                          Vazgeç
                        </button>
                        <button
                          type="button"
                          className="btn-primary btn-sm flex-1"
                          onClick={() => remove(item)}
                          disabled={busy}
                        >
                          {busy ? 'Siliniyor…' : 'Evet, sil'}
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-wrap items-center gap-1">
                      <button
                        type="button"
                        className="btn-secondary btn-sm"
                        onClick={() => setEditingId(item.id)}
                      >
                        <Pencil size={14} strokeWidth={1.5} aria-hidden /> Düzenle
                      </button>
                      <button
                        type="button"
                        className="btn-ghost btn-sm"
                        onClick={() => togglePublished(item)}
                        disabled={busy}
                        aria-label={item.isPublished ? 'Gizle' : 'Yayınla'}
                      >
                        {item.isPublished ? (
                          <EyeOff size={14} strokeWidth={1.5} aria-hidden />
                        ) : (
                          <Eye size={14} strokeWidth={1.5} aria-hidden />
                        )}
                        {item.isPublished ? 'Gizle' : 'Yayınla'}
                      </button>
                      <div className="ml-auto flex items-center">
                        <button
                          type="button"
                          className="btn-ghost btn-sm"
                          onClick={() => move(index, -1)}
                          disabled={index === 0}
                          aria-label="Yukarı taşı"
                        >
                          <ArrowUp size={14} strokeWidth={1.5} aria-hidden />
                        </button>
                        <button
                          type="button"
                          className="btn-ghost btn-sm"
                          onClick={() => move(index, 1)}
                          disabled={index === items.length - 1}
                          aria-label="Aşağı taşı"
                        >
                          <ArrowDown size={14} strokeWidth={1.5} aria-hidden />
                        </button>
                        <button
                          type="button"
                          className="btn-ghost btn-sm text-rose-700"
                          onClick={() => setConfirmId(item.id)}
                          aria-label="Sil"
                        >
                          <Trash2 size={14} strokeWidth={1.5} aria-hidden />
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}

function UploadForm({ categories, staff }: { categories: Option[]; staff: Option[] }) {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [categoryId, setCategoryId] = useState('');
  const [staffId, setStaffId] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(event: React.FormEvent<HTMLFormElement>) {
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
      event.currentTarget.reset();
      router.refresh();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Yükleme başarısız.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={upload} className="card grid grid-cols-1 gap-2 !p-3 md:grid-cols-2">
      <p className="label flex items-center gap-1.5 md:col-span-2">
        <ImagePlus size={14} strokeWidth={1.5} aria-hidden /> Yeni iş ekle
      </p>
      <input
        type="file"
        accept="image/jpeg,image/png,image/webp"
        className="field md:col-span-2"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <input
        className="field"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Başlık (örn. Balyaj — Küllü Kumral)"
        required
      />
      <input
        className="field"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Açıklama (isteğe bağlı)"
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
        <option value="">Personel (varsayılan: sen)</option>
        {staff.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
      {error && (
        <p role="alert" className="text-sm text-danger-700 md:col-span-2">
          {error}
        </p>
      )}
      <button className="btn-primary btn-sm md:col-span-2" disabled={busy || !file || !title}>
        {busy ? 'Yükleniyor…' : 'Galeriye ekle'}
      </button>
    </form>
  );
}

function EditPanel({
  item,
  categories,
  staff,
  onClose,
  onSaved,
}: {
  item: Item;
  categories: Option[];
  staff: Option[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(item.description ?? '');
  const [categoryId, setCategoryId] = useState(item.categoryId ? String(item.categoryId) : '');
  const [staffId, setStaffId] = useState(item.staffId ? String(item.staffId) : '');
  const [isPublished, setIsPublished] = useState(item.isPublished);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append('title', title);
      form.append('description', description);
      form.append('categoryId', categoryId);
      form.append('staffId', staffId);
      form.append('isPublished', String(isPublished));
      if (file) form.append('file', file);
      await apiUpload(`/api/admin/portfolio/${item.id}`, form, 'PATCH');
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Kaydedilemedi.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={save} className="grid grid-cols-1 gap-2 pt-1 md:grid-cols-2">
      <label className="block">
        <span className="label">Başlık</span>
        <input
          className="field"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
          maxLength={160}
        />
      </label>
      <label className="block">
        <span className="label">Açıklama</span>
        <input
          className="field"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </label>
      <label className="block">
        <span className="label">Kategori</span>
        <select className="field" value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">Kategori yok</option>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="label">Personel</span>
        <select className="field" value={staffId} onChange={(e) => setStaffId(e.target.value)}>
          <option value="">Belirtilmedi</option>
          {staff.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </label>
      <label className="block md:col-span-2">
        <span className="label">Görseli değiştir</span>
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className="field"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </label>
      <label className="flex items-center gap-2 text-sm md:col-span-2">
        <input
          type="checkbox"
          checked={isPublished}
          onChange={(e) => setIsPublished(e.target.checked)}
        />
        Yayında
      </label>
      {error && (
        <p role="alert" className="text-sm text-danger-700 md:col-span-2">
          {error}
        </p>
      )}
      <div className="flex gap-1 md:col-span-2">
        <button type="button" className="btn-secondary btn-sm flex-1" onClick={onClose} disabled={busy}>
          Vazgeç
        </button>
        <button className="btn-primary btn-sm flex-1" disabled={busy || !title.trim()}>
          {busy ? 'Kaydediliyor…' : 'Kaydet'}
        </button>
      </div>
    </form>
  );
}
