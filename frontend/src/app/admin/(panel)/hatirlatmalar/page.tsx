import { adminApi } from '@/lib/admin-api';
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
  FIXED: 'Sabit aralık — her zaman `baseDays` kadar sonra hatırlatır.',
  GROWTH:
    'Büyüme modeli — saç ~mmPerMonth kadar uzar, toleranceMm mm dip görününce hatırlatır. Gün sayısı formülden çıkar.',
  PRODUCT_LIFETIME:
    'Ürün ömrü — kullanılan ürünün (kalıcı oje / jel / klasik oje) dayanma süresine göre hatırlatır.',
  SEASONAL: 'Mevsimsel — ay çarpanıyla aralık kısalır/uzar (kışın cilt bakımı daha sık).',
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
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="section-title">Hatırlatma kuralları</h1>
          <p className="muted">Aralıklar formülden hesaplanır — kodda sabit gün yoktur.</p>
        </div>
        <SweepButton pendingDue={pendingDue} />
      </div>

      <div className="space-y-3">
        {rules.map((r) => {
          const params = r.params;
          // Önizleme FastAPI'de `compute_interval_days` ile hesaplanır.
          const previewDays = r.samplePreviewDays;

          return (
            <article key={r.id} className="card">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h2 className="font-semibold">
                    {r.name}
                    {!r.isActive && (
                      <span className="badge ml-2 bg-sand-100 text-ink-500">pasif</span>
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
                  <p className="text-2xl font-semibold tabular-nums">{previewDays} gün</p>
                  <p className="muted">bugün uygulansaydı</p>
                </div>
              </div>

              <p className="mt-2 rounded-xl bg-sand-100 px-3 py-2 text-sm">
                <strong>{r.formula}</strong> — {FORMULA_HELP[r.formula]}
              </p>

              {Object.keys(params).length > 0 && (
                <pre className="mt-2 overflow-x-auto rounded-xl bg-ink-900/90 p-3 text-xs text-sand-100">
                  {JSON.stringify(params, null, 2)}
                </pre>
              )}

              <p className="mt-2 text-sm italic text-ink-500">&quot;{r.template}&quot;</p>
            </article>
          );
        })}
      </div>

      {/* ---------------- Bildirim kuyruğu ---------------- */}
      <section className="card">
        <h2 className="section-title">Bildirim kuyruğu</h2>
        <p className="muted">
          Mesajlar WhatsApp üzerinden gönderilir (geliştirmede sunucu log&apos;una yazılır).
          &quot;Kuyruğu işle&quot; zamanı gelenleri hemen gönderir; gönderilemeyenler birkaç kez
          yeniden denenir, sonra <code>FAILED</code> olur.
        </p>
        <ul className="mt-3 divide-y divide-sand-100">
          {queue.map((n) => (
            <li key={n.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
              <div className="min-w-0">
                <p className="truncate">{n.body}</p>
                <p className="muted">
                  {n.customer.firstName} · 0{n.customer.phone} ·{' '}
                  {n.dueAt.toLocaleDateString('tr-TR')} {n.dueAt.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}
                </p>
              </div>
              <span
                className={`badge ${
                  n.status === 'SENT'
                    ? 'bg-emerald-50 text-emerald-700'
                    : n.dueAt <= now
                      ? 'bg-amber-50 text-amber-800'
                      : 'bg-sand-100 text-ink-500'
                }`}
              >
                {n.status === 'SENT' ? 'gönderildi' : n.dueAt <= now ? 'zamanı geldi' : 'bekliyor'}
              </span>
            </li>
          ))}
          {queue.length === 0 && <li className="muted py-2">Kuyruk boş.</li>}
        </ul>
      </section>
    </div>
  );
}
