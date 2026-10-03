'use client';

import { ChevronDown } from 'lucide-react';
import { useState } from 'react';

import { ApiError, apiSend } from '@/lib/api-client';

export interface RebookingRule {
  id: number;
  isActive: boolean;
  baseDays: number;
  formula: string;
  /** FIXED değilse süre formülden gelir; salt-okunur gösterilir. */
  advanced: boolean;
  template: string;
}

export interface RebookingService {
  id: number;
  name: string;
  rule: RebookingRule | null;
  /** Hizmete özel kural yok ama kategori/genel kural bu hizmeti kapsıyor. */
  inheritedRuleName: string | null;
}

export interface RebookingData {
  groups: { category: { id: number | null; name: string }; services: RebookingService[] }[];
  defaultTemplate: string;
  placeholders: Record<string, string>;
  optOutLine: string;
  maxTemplateLength: number;
  marketingConsentCount: number;
}

type Unit = 'gun' | 'hafta' | 'ay';
const UNIT_DAYS: Record<Unit, number> = { gun: 1, hafta: 7, ay: 30 };
const UNIT_LABEL: Record<Unit, string> = { gun: 'gün', hafta: 'hafta', ay: 'ay' };

/** 90 gün -> 3 ay, 14 gün -> 2 hafta, aksi halde gün. */
function splitDays(days: number): { amount: number; unit: Unit } {
  if (days >= 30 && days % 30 === 0) return { amount: days / 30, unit: 'ay' };
  if (days >= 7 && days % 7 === 0) return { amount: days / 7, unit: 'hafta' };
  return { amount: days, unit: 'gun' };
}

function describeAdvanced(r: RebookingRule): string {
  switch (r.formula) {
    case 'GROWTH':
      return 'Saç uzama hızına göre hesaplanıyor';
    case 'PRODUCT_LIFETIME':
      return 'Kullanılan ürünün ömrüne göre hesaplanıyor';
    case 'SEASONAL':
      return 'Mevsime göre hesaplanıyor';
    default:
      return 'Gelişmiş formül';
  }
}

/**
 * Hizmet bazlı yenileme daveti: "Saç boyama 3 ay sonra, manikür 2 hafta sonra".
 * Randevu Tamamlandı olunca, hizmetin kuralı kadar sonra müşteriye WhatsApp'tan
 * randevu daveti gider. Ticari ileti olduğu için yalnızca ileti onayı vermiş
 * müşterilere gönderilir ve "RET" yazarak çıkış hakkı sunulur.
 */
export function RebookingSettings({ initial }: { initial: RebookingData }) {
  const [data, setData] = useState(initial);

  return (
    <section className="card space-y-3 !p-4">
      <div>
        <h2 className="eyebrow">Yenileme daveti</h2>
        <p className="muted mt-1 text-sm">
          Hizmet tamamlandıktan belirlediğiniz süre sonra müşteriye randevu daveti gider. Kapalı
          hizmetlere mesaj gönderilmez.
        </p>
        <p className="mt-1 text-xs text-ink-500">
          Şu an <strong className="tabular-nums">{data.marketingConsentCount}</strong> müşteri ticari
          ileti onayı vermiş. Davetler yalnızca onay veren müşterilere gider; mesajın sonuna çıkış
          satırı eklenir: <em>&quot;{data.optOutLine}&quot;</em>
        </p>
      </div>

      {data.groups.map((group) => (
        <div key={group.category.id ?? 'diger'} className="space-y-1.5">
          <h3 className="label !mb-0">{group.category.name}</h3>
          <ul className="divide-y divide-sand-100 rounded-2xl border border-sand-200">
            {group.services.map((service) => (
              <ServiceRow key={service.id} service={service} data={data} onData={setData} />
            ))}
          </ul>
        </div>
      ))}
      {data.groups.length === 0 && <p className="muted text-sm">Tanımlı hizmet yok.</p>}
    </section>
  );
}

function ServiceRow({
  service,
  data,
  onData,
}: {
  service: RebookingService;
  data: RebookingData;
  onData: (next: RebookingData) => void;
}) {
  const rule = service.rule;
  const initialSplit = splitDays(rule?.baseDays ?? 30);
  const [enabled, setEnabled] = useState(rule?.isActive ?? false);
  const [amount, setAmount] = useState(String(initialSplit.amount));
  const [unit, setUnit] = useState<Unit>(initialSplit.unit);
  const [template, setTemplate] = useState(rule?.template ?? data.defaultTemplate);
  const [advanced, setAdvanced] = useState(rule?.advanced ?? false);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const amountNum = Number.parseInt(amount, 10);
  const days = amountNum * UNIT_DAYS[unit];
  const daysValid = Number.isInteger(amountNum) && amountNum >= 1 && days <= 400;

  async function persist(nextEnabled: boolean, switchToSimple = false) {
    if (nextEnabled && (!daysValid || (advanced && !switchToSimple && !rule))) {
      setError('Geçerli bir süre girin (en fazla 400 gün).');
      return;
    }
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      const next = await apiSend<RebookingData>('/api/admin/rebooking', 'PUT', {
        serviceId: service.id,
        enabled: nextEnabled,
        baseDays: daysValid && (!advanced || switchToSimple) ? days : undefined,
        template,
        switchToSimple,
      });
      const row = next.groups.flatMap((g) => g.services).find((s) => s.id === service.id);
      setEnabled(row?.rule?.isActive ?? false);
      setAdvanced(row?.rule?.advanced ?? false);
      setSaved(true);
      onData(next);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Kaydedilemedi.');
    } finally {
      setBusy(false);
    }
  }

  const durationText = advanced
    ? describeAdvanced(rule!)
    : daysValid
      ? `${amountNum} ${UNIT_LABEL[unit]} sonra`
      : '—';

  return (
    <li className="space-y-2 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-medium text-ink-900">{service.name}</p>
          {!enabled && !rule && service.inheritedRuleName && (
            <p className="text-xs text-ink-500">
              Kendi kuralı yok; &quot;{service.inheritedRuleName}&quot; kuralı geçerli.
            </p>
          )}
          {enabled && <p className="text-xs text-ink-500">{durationText}</p>}
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm">
          <input
            type="checkbox"
            role="switch"
            className="h-5 w-5 accent-plum-600"
            checked={enabled}
            disabled={busy}
            onChange={(e) => {
              setEnabled(e.target.checked);
              void persist(e.target.checked);
            }}
            aria-label={`${service.name} yenileme daveti`}
          />
          <span className="w-12 text-xs text-ink-500">{enabled ? 'Açık' : 'Kapalı'}</span>
        </label>
      </div>

      {enabled && (
        <div className="space-y-2">
          {advanced ? (
            <div className="rounded-2xl bg-sand-100 px-3 py-2 text-xs text-ink-700">
              <p>
                {describeAdvanced(rule!)} (yaklaşık {rule!.baseDays} gün). Bu süre formülden gelir,
                burada değiştirilemez.
              </p>
              <button
                type="button"
                className="btn-ghost btn-sm mt-1.5"
                disabled={busy || !daysValid}
                onClick={() => void persist(true, true)}
              >
                Basit süreye geç ({daysValid ? `${amountNum} ${UNIT_LABEL[unit]}` : 'süre girin'})
              </button>
              <div className="mt-1.5 flex items-center gap-2">
                <DurationInputs amount={amount} unit={unit} setAmount={setAmount} setUnit={setUnit} id={service.id} />
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <DurationInputs amount={amount} unit={unit} setAmount={setAmount} setUnit={setUnit} id={service.id} />
              <span className="text-sm text-ink-700">sonra</span>
              <button
                type="button"
                className="btn-primary btn-sm ml-auto"
                disabled={busy || !daysValid}
                onClick={() => void persist(true)}
              >
                Kaydet
              </button>
            </div>
          )}

          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs text-plum-700"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            <ChevronDown size={14} strokeWidth={1.5} className={open ? 'rotate-180' : ''} aria-hidden />
            Mesajı düzenle
          </button>

          {open && (
            <div className="space-y-2">
              <textarea
                className="field min-h-24"
                aria-label={`${service.name} davet mesajı`}
                maxLength={data.maxTemplateLength}
                value={template}
                onChange={(e) => setTemplate(e.target.value)}
              />
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-ink-500">
                {Object.entries(data.placeholders).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    className="btn-ghost btn-sm !px-2.5 !py-1 text-xs"
                    title={label}
                    onClick={() => setTemplate((t) => `${t}${t.endsWith(' ') || !t ? '' : ' '}${key}`)}
                  >
                    {key}
                  </button>
                ))}
                <span className="ml-auto tabular-nums">
                  {template.length}/{data.maxTemplateLength}
                </span>
              </div>
              <p className="text-xs text-ink-500">
                Sona otomatik eklenir: <em>{data.optOutLine}</em>
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className="btn-primary btn-sm"
                  disabled={busy || !template.trim() || (!advanced && !daysValid)}
                  onClick={() => void persist(true)}
                >
                  Mesajı kaydet
                </button>
                {template !== data.defaultTemplate && (
                  <button type="button" className="btn-ghost btn-sm" onClick={() => setTemplate(data.defaultTemplate)}>
                    Varsayılan metne dön
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {error && <p className="text-sm text-danger-700">{error}</p>}
      {saved && !error && <p className="text-xs text-success-700">Kaydedildi.</p>}
    </li>
  );
}

function DurationInputs({
  amount,
  unit,
  setAmount,
  setUnit,
  id,
}: {
  amount: string;
  unit: Unit;
  setAmount: (v: string) => void;
  setUnit: (v: Unit) => void;
  id: number;
}) {
  return (
    <>
      <input
        id={`rb-amount-${id}`}
        type="number"
        inputMode="numeric"
        min={1}
        className="field !w-20"
        aria-label="Süre"
        value={amount}
        onChange={(e) => setAmount(e.target.value)}
      />
      <select
        className="field !w-28"
        aria-label="Süre birimi"
        value={unit}
        onChange={(e) => setUnit(e.target.value as Unit)}
      >
        <option value="gun">gün</option>
        <option value="hafta">hafta</option>
        <option value="ay">ay</option>
      </select>
    </>
  );
}
