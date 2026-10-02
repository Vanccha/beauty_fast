'use client';

import { ChevronDown } from 'lucide-react';
import { useState } from 'react';

import { COUNTRIES, DEFAULT_DIAL, composePhone } from '@/lib/phone';

/** `+905321234567` → { dial: '90', local: '5321234567' }; tanınmayan kod olduğu gibi kalır. */
function splitPhone(value: string): { dial: string; local: string } {
  const v = value.trim();
  if (!v.startsWith('+')) return { dial: DEFAULT_DIAL, local: v };
  const digits = v.replace(/\D/g, '');
  const match = [...COUNTRIES]
    .sort((a, b) => b.dial.length - a.dial.length)
    .find((c) => digits.startsWith(c.dial));
  return match ? { dial: match.dial, local: digits.slice(match.dial.length) } : { dial: DEFAULT_DIAL, local: v };
}

/**
 * Ülke kodlu telefon alanı. Ülke kodu hazır seçili gelir (Türkiye +90);
 * yurtdışı numara için seçiciden ülke seçilir ya da numara `+` ile tam yazılır.
 *
 * `onChange` backend'e gönderilecek numarayı verir (ör. `+905321234567`,
 * `+447911123456`); doğrulama `normalizePhone` + `isValidMobile` ile yapılır.
 */
export function PhoneInput({
  id,
  defaultValue = '',
  onChange,
  autoFocus,
  required,
  autoComplete = 'tel-national',
}: {
  id: string;
  /** Başlangıç değeri (ör. taslaktan geri yüklenen numara). Sonradan değişirse bileşene yeni `key` verin. */
  defaultValue?: string;
  onChange: (phone: string) => void;
  autoFocus?: boolean;
  required?: boolean;
  autoComplete?: string;
}) {
  const [dial, setDial] = useState(() => splitPhone(defaultValue).dial);
  const [local, setLocal] = useState(() => splitPhone(defaultValue).local);

  const typedFull = local.trim().startsWith('+');
  const placeholder = dial === DEFAULT_DIAL ? '532 000 00 00' : 'Numara';

  return (
    <div className="flex gap-2">
      <div className="relative shrink-0">
        <select
          aria-label="Ülke kodu"
          value={dial}
          disabled={typedFull}
          onChange={(e) => {
            setDial(e.target.value);
            onChange(composePhone(e.target.value, local));
          }}
          className="field h-full !w-[6.75rem] appearance-none !pr-7 tabular-nums disabled:opacity-40"
        >
          {COUNTRIES.map((c) => (
            <option key={c.iso} value={c.dial}>
              {c.iso} +{c.dial}
              {c.iso === 'US' ? ' (ABD/Kanada)' : ''}
            </option>
          ))}
        </select>
        <ChevronDown
          size={14}
          strokeWidth={1.75}
          aria-hidden
          className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-ink-500"
        />
      </div>
      <input
        id={id}
        className="field min-w-0 flex-1 tabular-nums"
        value={local}
        onChange={(e) => {
          setLocal(e.target.value);
          onChange(composePhone(dial, e.target.value));
        }}
        inputMode="tel"
        autoComplete={autoComplete}
        placeholder={placeholder}
        autoFocus={autoFocus}
        required={required}
      />
    </div>
  );
}
