/**
 * Telefon numaraları — backend'deki `normalize_phone` / `is_valid_mobile`
 * (backend/app/core/risk_score.py) ile AYNI kurallar.
 *
 * Saklama biçimi:
 *   - Türkiye: 10 hane, `5XXXXXXXXX` (mevcut kayıtlar bu biçimde)
 *   - Yurtdışı: E.164, `+447911123456`
 */

export interface Country {
  /** ISO kodu (seçicide gösterilir) */
  iso: string;
  name: string;
  /** Ülke kodu, + olmadan */
  dial: string;
}

/** Varsayılan Türkiye; ardından salon müşterilerinde sık görülen ülkeler. */
export const COUNTRIES: Country[] = [
  { iso: 'TR', name: 'Türkiye', dial: '90' },
  { iso: 'DE', name: 'Almanya', dial: '49' },
  { iso: 'GB', name: 'Birleşik Krallık', dial: '44' },
  { iso: 'NL', name: 'Hollanda', dial: '31' },
  { iso: 'FR', name: 'Fransa', dial: '33' },
  { iso: 'BE', name: 'Belçika', dial: '32' },
  { iso: 'AT', name: 'Avusturya', dial: '43' },
  { iso: 'CH', name: 'İsviçre', dial: '41' },
  { iso: 'SE', name: 'İsveç', dial: '46' },
  { iso: 'IT', name: 'İtalya', dial: '39' },
  { iso: 'ES', name: 'İspanya', dial: '34' },
  { iso: 'GR', name: 'Yunanistan', dial: '30' },
  { iso: 'BG', name: 'Bulgaristan', dial: '359' },
  { iso: 'CY', name: 'Kıbrıs', dial: '357' },
  { iso: 'AZ', name: 'Azerbaycan', dial: '994' },
  { iso: 'GE', name: 'Gürcistan', dial: '995' },
  { iso: 'RU', name: 'Rusya', dial: '7' },
  { iso: 'UA', name: 'Ukrayna', dial: '380' },
  { iso: 'IR', name: 'İran', dial: '98' },
  { iso: 'IQ', name: 'Irak', dial: '964' },
  { iso: 'SA', name: 'Suudi Arabistan', dial: '966' },
  { iso: 'AE', name: 'BAE', dial: '971' },
  { iso: 'QA', name: 'Katar', dial: '974' },
  { iso: 'US', name: 'ABD / Kanada', dial: '1' },
];

export const DEFAULT_DIAL = '90';

/** Girilen numarayı saklama biçimine getirir (geçerliliğe bakmaz). */
export function normalizePhone(raw: string): string {
  const trimmed = raw.trim();
  let digits = trimmed.replace(/\D/g, '');
  const international = trimmed.startsWith('+') || digits.startsWith('00');
  if (international) {
    if (digits.startsWith('00')) digits = digits.slice(2);
    if (digits.startsWith('90')) {
      const local = digits.slice(2);
      return local.length > 10 ? local.slice(-10) : local;
    }
    return digits ? `+${digits}` : '';
  }
  return digits.length > 10 ? digits.slice(-10) : digits;
}

/** `normalizePhone` çıktısı geçerli bir cep numarası mı? */
export function isValidMobile(phone: string): boolean {
  return /^5\d{9}$/.test(phone) || /^\+[1-9]\d{6,14}$/.test(phone);
}

/** Seçilen ülke kodu + yerel numara → backend'e gönderilecek numara.
 *  Kullanıcı numarayı `+` veya `00` ile tam yazdıysa seçici yok sayılır. */
export function composePhone(dial: string, local: string): string {
  const t = local.trim();
  if (!t) return '';
  if (t.startsWith('+') || t.replace(/\D/g, '').startsWith('00')) return t;
  const digits = t.replace(/\D/g, '').replace(/^0+/, '');
  return `+${dial}${digits}`;
}

/** Saklanan numarayı okunur gösterir: `0555 111 22 33` ya da `+447911123456`. */
export function formatPhone(phone: string | null | undefined): string {
  if (!phone) return '';
  if (phone.startsWith('+')) return phone;
  if (/^\d{10}$/.test(phone)) {
    return `0${phone.slice(0, 3)} ${phone.slice(3, 6)} ${phone.slice(6, 8)} ${phone.slice(8)}`;
  }
  return phone;
}

/** `tel:` bağlantısı için. */
export function telHref(phone: string): string {
  return phone.startsWith('+') ? `tel:${phone}` : `tel:+90${phone}`;
}
