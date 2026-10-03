'use client';

import Link from 'next/link';
import { useId } from 'react';

const ROW = 'flex min-h-11 cursor-pointer items-start gap-3 py-2';
const BOX = 'mt-0.5 h-4 w-4 shrink-0 accent-plum-600';
const TEXT = 'text-sm text-ink-700';
const LINK = 'font-medium text-plum-600 underline underline-offset-2';

/**
 * Zorunlu iki onay: KVKK aydınlatma metnini okuduğunu bildirme (rıza DEĞİL,
 * bilgilendirme teyidi) ve sağlık beyanı. İkisi bilerek ayrı kutulardır.
 */
export function RequiredConsents({
  privacyAck,
  onPrivacyAck,
  healthDecl,
  onHealthDecl,
}: {
  privacyAck: boolean;
  onPrivacyAck: (v: boolean) => void;
  healthDecl: boolean;
  onHealthDecl: (v: boolean) => void;
}) {
  const id = useId();
  return (
    <div className="space-y-1">
      <label htmlFor={`${id}-kvkk`} className={ROW}>
        <input
          id={`${id}-kvkk`}
          type="checkbox"
          className={BOX}
          checked={privacyAck}
          onChange={(e) => onPrivacyAck(e.target.checked)}
        />
        <span className={TEXT}>
          <Link href="/kvkk" target="_blank" className={LINK}>
            KVKK Aydınlatma Metni
          </Link>
          &apos;ni okudum.
        </span>
      </label>
      <label htmlFor={`${id}-health`} className={ROW}>
        <input
          id={`${id}-health`}
          type="checkbox"
          className={BOX}
          checked={healthDecl}
          onChange={(e) => onHealthDecl(e.target.checked)}
        />
        <span className={TEXT}>
          Alerji, hamilelik, cilt hassasiyeti veya kullandığım ilaçlar gibi işlemi etkileyebilecek
          bir durumum varsa bunu personele bildireceğimi beyan ederim.
        </span>
      </label>
    </div>
  );
}

export interface AllergyState {
  enabled: boolean;
  label: string;
  note: string;
  consent: boolean;
}

export const EMPTY_ALLERGY: AllergyState = { enabled: false, label: '', note: '', consent: false };

/** Gönderilecek alerji gövdesi; koşullar sağlanmıyorsa null. */
export function allergyPayload(a: AllergyState) {
  const label = a.label.trim();
  if (!a.enabled || !label || !a.consent) return null;
  return { allergy: { label, note: a.note.trim() || null }, healthConsent: true as const };
}

/** İsteğe bağlı alerji kaydı + ayrı açık rıza. Yalnızca bellekte tutulur. */
export function AllergyOptIn({
  value,
  onChange,
}: {
  value: AllergyState;
  onChange: (v: AllergyState) => void;
}) {
  const id = useId();
  const set = (p: Partial<AllergyState>) => onChange({ ...value, ...p });
  const hasLabel = value.label.trim().length > 0;
  return (
    <div className="mt-3 space-y-2 border-t border-sand-200 pt-3">
      <label htmlFor={`${id}-on`} className={ROW}>
        <input
          id={`${id}-on`}
          type="checkbox"
          className={BOX}
          checked={value.enabled}
          onChange={(e) => set({ enabled: e.target.checked })}
        />
        <span className={TEXT}>
          <span className="font-medium">Alerjimi kaydet (isteğe bağlı)</span>
          <span className="mt-0.5 block text-xs text-ink-500">
            İşaretlemezsen randevun yine oluşur; alerjini salonda sözlü de bildirebilirsin.
          </span>
        </span>
      </label>

      {value.enabled && (
        <div className="space-y-3 rounded-2xl bg-sand-50 p-3">
          <div>
            <label className="label" htmlFor={`${id}-label`}>
              Alerji / hassasiyet
            </label>
            <input
              id={`${id}-label`}
              className="field"
              maxLength={120}
              value={value.label}
              onChange={(e) => set({ label: e.target.value })}
              placeholder="Örn. amonyak, lateks, parfüm"
            />
          </div>
          <div>
            <label className="label" htmlFor={`${id}-note`}>
              Not (isteğe bağlı)
            </label>
            <textarea
              id={`${id}-note`}
              className="field"
              rows={2}
              maxLength={500}
              value={value.note}
              onChange={(e) => set({ note: e.target.value })}
            />
          </div>
          <label htmlFor={`${id}-consent`} className={ROW}>
            <input
              id={`${id}-consent`}
              type="checkbox"
              className={BOX}
              checked={value.consent}
              onChange={(e) => set({ consent: e.target.checked })}
            />
            <span className={TEXT}>
              Alerji bilgimin, işlem öncesinde personele uyarı olarak gösterilmesi amacıyla müşteri
              kartıma kaydedilmesine{' '}
              <Link href="/acik-riza#saglik" target="_blank" className={LINK}>
                Açık Rıza Metni
              </Link>{' '}
              kapsamında açık rıza veriyorum.
            </span>
          </label>
          {hasLabel && !value.consent && (
            <p className="text-xs text-ink-500" role="status">
              Açık rıza vermezsen alerji bilgin kaydedilmez; randevun yine oluşur.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
