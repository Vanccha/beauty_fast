/**
 * KVKK metinlerinin (`/kvkk`, `/acik-riza`, `/cerez-politikasi`) ortak
 * bilgileri.
 *
 * Salon adı, şube adresi ve telefonu metinlere sistemden (`/api/showcase`)
 * gelir. Burada yalnızca sistemde tutulmayan YASAL KİMLİK bilgileri durur.
 *
 * ⚠️ TEMSİLİ: Aşağıdaki değerler örnektir. Gerçek bir salonda canlıya
 * çıkmadan önce salonun kendi bilgileriyle değiştirilmeli ve metinler bir
 * hukukçuya gözden geçirtilmelidir (DEGISIKLIKLER_V3.md). `isRepresentative`
 * true olduğu sürece her metnin başında uyarı görünür.
 */
export const LEGAL = {
  isRepresentative: true,

  /** Veri sorumlusunun ticari unvanı (şahıs işletmesiyse ad soyad). */
  controllerTitle: 'Aurora Güzellik Hizmetleri Ltd. Şti.',
  mersisNo: '0000-0000-0000-0000',
  taxInfo: 'Kadıköy V.D. — 0000000000',
  /** Başvuruların yazılı iletileceği e-posta ve KEP adresi. */
  email: 'kvkk@aurora-ornek.com.tr',
  kepAddress: 'aurora@hs01.kep.tr',

  lastUpdated: '1 Ekim 2026',
} as const;

/**
 * Saklama süreleri. Kaynak: backend `app/services/privacy.py` ve
 * `app/auth/sessions.py`. Biri değişirse diğeri de güncellenmeli.
 */
export const RETENTION = {
  otpMinutes: 5,
  customerSessionDays: 180,
  staffSessionDays: 7,
  visitorKeyDays: 180,
  slotViewDays: 30,
  notificationDays: 180,
  riskEventMonths: 12,
} as const;
