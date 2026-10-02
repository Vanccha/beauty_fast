import { adminApi } from '@/lib/admin-api';
import { formatPhone } from '@/lib/phone';
import { SweepButton } from './sweep-button';

export const dynamic = 'force-dynamic';

interface ReminderRuleRow {
  id: number;
  name: string;
  service: { id: number; name: string } | null;
  category: { id: number; name: string } | null;
  formula: string;
  baseDays: number;
  params: Record<string, unknown>;
  preReminderHours: number | null;
  channel: string;
  template: string;
  priority: number;
  isActive: boolean;
  previewDays: number;
  /** PRODUCT_LIFETIME için örnek ürünle ("kalici_oje") hesaplanmış önizleme */
  samplePreviewDays: number;
}

interface QueuedNotification {
  id: number;
  channel: string;
  body: string;
  status: string;
  dueAt: string;
  sentAt: string | null;
  customer: { firstName: string; phone: string };
}

const FORMULA_HELP: Record<string, string> = {
  FIXED: 'Sabit aralık — her zaman temel gün sayısı kadar sonra hatırlatır.',
  GROWTH:
    'Büyüme modeli — saç her ay belirli bir miktar uzar; dip toleransı aşılınca hatırlatır. Gün sayısı formülden çıkar.',
  PRODUCT_LIFETIME:
    'Ürün ömrü — kullanılan ürünün (kalıcı oje / jel / klasik oje) dayanma süresine göre hatırlatır.',
  SEASONAL: 'Mevsimsel — ay çarpanıyla aralık kısalır/uzar (kışın cilt bakımı daha sık).',
};

const PRODUCT_LABELS: Record<string, string> = {
  kalici_oje: 'Kalıcı oje',
  jel: 'Jel',
  klasik_oje: 'Klasik oje',
};

const MONTHS = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];

const num = (v: unknown) => String(v).replace('.', ',');

/** Kural parametreleri ham JSON yerine "etiket: değer" çiftleri olarak gösterilir. */
function describeParams(params: Record<string, unknown>): { label: string; value: string }[] {
  const out: { label: string; value: string }[] = [];
  for (const [key, value] of Object.entries(params)) {
    if (key === 'mmPerMonth') {
      out.push({ label: 'Uzama hızı', value: `${num(value)} mm/ay` });
    } else if (key === 'toleranceMm') {
      out.push({ label: 'Dip toleransı', value: `${num(value)} mm` });
    } else if (key === 'productDays' && value && typeof value === 'object') {
      for (const [product, days] of Object.entries(value)) {
        out.push({ label: PRODUCT_LABELS[product] ?? product.replace(/_/g, ' '), value: `${num(days)} gün` });
      }
    } else if (key === 'monthFactors' && value && typeof value === 'object') {
      const entries = Object.entries(value).sort(([a], [b]) => Number(a) - Number(b));
      for (const [month, factor] of entries) {
        const f = Number(factor);
        const effect = f < 1 ? 'daha sık' : f > 1 ? 'daha seyrek' : 'değişmez';
        out.push({ label: MONTHS[Number(month) - 1] ?? `${month}. ay`, value: `×${num(f)} (${effect})` });
      }
    } else {
      // Bilinmeyen anahtar: yine de JSON değil, düz metin.
      out.push({ label: key, value: typeof value === 'object' ? Object.values(value ?? {}).join(', ') : String(value) });
    }
  }
  return out;
}

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  SENT: { label: 'gönderildi', className: 'border border-emerald-300 bg-transparent text-emerald-700' },
  SENDING: { label: 'gönderiliyor', className: 'border border-sand-300 bg-transparent text-ink-700' },
  FAILED: { label: 'gönderilemedi', className: 'border border-rose-300 bg-transparent text-rose-700' },
  CANCELLED: { label: 'iptal', className: 'border border-sand-200 bg-sand-100 text-ink-400 line-through' },
};

/**
 * ====================================================================
 * HATIRLATMA KURALLARI
 * ====================================================================
 *
 * Hatırlatma aralıkları koda GÖMÜLÜ DEĞİLDİR: `ReminderRule` tablosundaki
 * formül + parametrelerden hesaplanır. Bu sayfa her kural için bugünün
 * koşullarıyla "kaç gün sonrasına kurulurdu" önizlemesini gösterir, böylece
 * yönetici formülü okumadan etkisini görür.
 *
 * Kural seçim önceliği: hizmet eşleşmesi > kategori > şube geneli;
 * eşitlikte `priority` büyük olan kazanır.
 */
export default async function ReminderRulesPage() {
  const now = new Date();

  const [{ rules }, { notifications }] = await Promise.all([
    adminApi<{ rules: ReminderRuleRow[] }>('/api/admin/reminder-rules'),
    adminApi<{ notifications: QueuedNotification[] }>('/api/admin/notifications?limit=25'),
  ]);

  const queue = notifications.map((n) => ({ ...n, dueAt: new Date(n.dueAt) }));

  const pendingDue = queue.filter((n) => n.status === 'PENDING' && n.dueAt <= now).length;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="muted">Aralıklar formülden hesaplanır — kodda sabit gün yoktur.</p>
        <SweepButton pendingDue={pendingDue} />
      </div>

      <div className="space-y-2">
        {rules.map((r) => {
          const params = describeParams(r.params);
          // Önizleme FastAPI'de `compute_interval_days` ile hesaplanır.
          const previewDays = r.samplePreviewDays;

          return (
            <article key={r.id} className="card !p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="text-sm font-semibold text-ink-900">
                    {r.name}
                    {!r.isActive && (
                      <span className="badge ml-2 border border-sand-200 bg-sand-100 text-ink-500">pasif</span>
                    )}
                  </h2>
                  <p className="muted">
                    Kapsam:{' '}
                    {r.service
                      ? `hizmet — ${r.service.name}`
                      : r.category
                        ? `kategori — ${r.category.name}`
                        : 'şube geneli (yedek kural)'}
                    {' · '}öncelik {r.priority} · {r.channel}
                  </p>
                </div>
                <div className="text-right">
                  <p className="display text-2xl tabular-nums">{previewDays} gün</p>
                  <p className="muted text-xs">bugün uygulansaydı</p>
                </div>
              </div>

              <p className="mt-2 rounded-[2px] bg-sand-100 px-3 py-2 text-sm">
                {FORMULA_HELP[r.formula] ?? r.formula}
              </p>

              {params.length > 0 && (
                <dl className="mt-2 flex flex-wrap gap-1.5 text-sm">
                  {params.map((p) => (
                    <div key={p.label} className="rounded-[2px] border border-sand-200 px-2.5 py-1">
                      <dt className="inline text-ink-500">{p.label}: </dt>
                      <dd className="inline font-medium tabular-nums">{p.value}</dd>
                    </div>
                  ))}
                </dl>
              )}

              <p className="mt-2 text-sm italic text-ink-500">&quot;{r.template}&quot;</p>
            </article>
          );
        })}
      </div>

      {/* ---------------- Bildirim kuyruğu ---------------- */}
      <section className="card !p-4">
        <h2 className="eyebrow">Bildirim kuyruğu</h2>
        <p className="muted mt-1 text-xs">
          &quot;Kuyruğu işle&quot; zamanı gelenleri hemen gönderir; gönderilemeyenler birkaç kez
          yeniden denenir, sonra <code>FAILED</code> olur.
        </p>
        <ul className="mt-3 divide-y divide-sand-100">
          {queue.map((n) => (
            <li key={n.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <div className="min-w-0">
                <p className="truncate">{n.body}</p>
                <p className="muted">
                  {n.customer.firstName} · {formatPhone(n.customer.phone)} ·{' '}
                  {n.dueAt.toLocaleDateString('tr-TR')} {n.dueAt.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
              <span
                className={`badge ${
                  STATUS_BADGE[n.status]?.className ??
                  (n.dueAt <= now
                    ? 'border border-brass-300 bg-transparent text-brass-700'
                    : 'border border-sand-200 bg-sand-100 text-ink-500')
                }`}
              >
                {STATUS_BADGE[n.status]?.label ?? (n.dueAt <= now ? 'zamanı geldi' : 'bekliyor')}
              </span>
            </li>
          ))}
          {queue.length === 0 && <li className="muted py-2">Kuyruk boş.</li>}
        </ul>
      </section>
    </div>
  );
}
