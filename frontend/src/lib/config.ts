/**
 * Ortam değişkenlerinin tek okuma noktası. Tümü lokal çalışmaya göre
 * varsayılana sahiptir; .env olmadan da proje ayağa kalkar.
 */

function num(value: string | undefined, fallback: number): number {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

export const config = {
  /** Soft-lock ömrü (saniye) — varsayılan 5 dakika. */
  slotLockTtlSeconds: num(process.env.SLOT_LOCK_TTL_SECONDS, 300),

  /** Müsaitlik taramasının adım büyüklüğü (dakika). */
  slotGridMinutes: num(process.env.SLOT_GRID_MINUTES, 15),

  /**
   * Doluluk hücresi çözünürlüğü (dakika). OccupancyCell tablosundaki
   * unique constraint bu granularitede çalışır. DEĞİŞTİRİLİRSE mevcut
   * hücrelerin yeniden üretilmesi gerekir.
   */
  cellMinutes: 5,

  sessionSecret: process.env.SESSION_SECRET || 'lokal-gelistirme-anahtari',
  phoneHashSecret: process.env.PHONE_HASH_SECRET || 'lokal-telefon-hash-anahtari',

  notificationDriver: process.env.NOTIFICATION_DRIVER || 'console',
  /** Geliştirmede sabit OTP; boşsa rastgele üretilir. */
  devOtpCode: process.env.DEV_OTP_CODE || '',

  isProduction: process.env.NODE_ENV === 'production',
} as const;
