/**
 * Tarih/saat yardımcıları.
 *
 * Sistem, randevuları "YYYY-MM-DD" (yerel gün) + "gün içi dakika" olarak
 * saklar. Bu, saat dilimi/yaz saati kaymalarının randevu ızgarasını
 * bozmasını engeller: 10:00 randevusu her zaman 600'dür.
 */

export const MINUTES_PER_DAY = 1440;

/** "YYYY-MM-DD" */
export type DateKey = string;

export function toDateKey(d: Date): DateKey {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function parseDateKey(key: DateKey): Date {
  const [y, m, d] = key.split('-').map(Number);
  return new Date(y, (m ?? 1) - 1, d ?? 1);
}

export function isDateKey(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(parseDateKey(value).getTime());
}

/** 0 = Pazar ... 6 = Cumartesi */
export function weekdayOf(key: DateKey): number {
  return parseDateKey(key).getDay();
}

export function addDaysToKey(key: DateKey, days: number): DateKey {
  const d = parseDateKey(key);
  d.setDate(d.getDate() + days);
  return toDateKey(d);
}

export function daysBetweenKeys(a: DateKey, b: DateKey): number {
  const ms = parseDateKey(b).getTime() - parseDateKey(a).getTime();
  return Math.round(ms / 86_400_000);
}

/** 570 -> "09:30" */
export function minutesToLabel(min: number): string {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/** "09:30" -> 570 */
export function labelToMinutes(label: string): number {
  const [h, m] = label.split(':').map(Number);
  return (h ?? 0) * 60 + (m ?? 0);
}

/** Gün + dakikadan gerçek bir Date üretir (yerel saat). */
export function toDateTime(key: DateKey, minute: number): Date {
  const d = parseDateKey(key);
  d.setHours(0, minute, 0, 0);
  return d;
}

export function nowParts(now: Date = new Date()): { dateKey: DateKey; minute: number } {
  return { dateKey: toDateKey(now), minute: now.getHours() * 60 + now.getMinutes() };
}

/** Bir değeri ızgaraya yukarı yuvarlar (17 dk, 15'lik ızgara -> 30). */
export function ceilToGrid(minute: number, grid: number): number {
  if (grid <= 1) return minute;
  return Math.ceil(minute / grid) * grid;
}

export function floorToGrid(minute: number, grid: number): number {
  if (grid <= 1) return minute;
  return Math.floor(minute / grid) * grid;
}

const TR_WEEKDAYS = ['Pazar', 'Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi'];
const TR_MONTHS = [
  'Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
  'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık',
];

export function formatDateTr(key: DateKey): string {
  const d = parseDateKey(key);
  return `${d.getDate()} ${TR_MONTHS[d.getMonth()]} ${d.getFullYear()}, ${TR_WEEKDAYS[d.getDay()]}`;
}

export function weekdayNameTr(weekday: number): string {
  return TR_WEEKDAYS[weekday] ?? '';
}
