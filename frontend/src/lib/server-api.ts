import { cookies } from 'next/headers';

/**
 * ====================================================================
 * SUNUCU TARAFI API İSTEMCİSİ
 * ====================================================================
 *
 * Bu sürümde sayfalar veritabanına DOĞRUDAN erişmez. Next.js yalnızca
 * arayüzdür; tüm veri FastAPI backend'inden (`backend/app/`) gelir.
 *
 * Sunucu bileşenleri bu yardımcıyı kullanır: tarayıcının çerezlerini
 * (oturum + ziyaretçi anahtarı) isteğe iliştirir, böylece FastAPI
 * tarafındaki yetki kapıları aynı şekilde çalışır.
 *
 * İstemci bileşenleri ise değişmeden `/api/...` adreslerine istek atar;
 * `next.config.mjs` içindeki rewrite bunu aynı origin üzerinden backend'e
 * yönlendirir (çerezler bu sayede aynı origin'de kalır).
 */

/** Sunucudan sunucuya çağrı — tarayıcı üzerinden geçmez. */
const API_BASE = process.env.API_URL ?? 'http://127.0.0.1:8000';

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function cookieHeader(): Promise<string> {
  const jar = await cookies();
  return jar
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join('; ');
}

/**
 * FastAPI'den veri okur ve `{ ok, data }` zarfını açar.
 *
 * @param path `/api/...` ile başlayan yol
 */
export async function serverApi<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { cookie: await cookieHeader() },
    // Randevu verisi her istekte tazedir; önbellek yok.
    cache: 'no-store',
  });

  const body = (await response.json().catch(() => null)) as
    | { ok: true; data: T }
    | { ok: false; error: { code: string; message: string } }
    | null;

  if (!body || !('ok' in body)) {
    throw new ApiError('INTERNAL', 'Sunucu yanıtı okunamadı.', response.status);
  }
  if (!body.ok) {
    throw new ApiError(body.error.code, body.error.message, response.status);
  }
  return body.data;
}

/**
 * Hata durumunda `null` döner — "oturum yoksa misafir göster" gibi
 * akışlarda try/catch tekrarını önler.
 */
export async function serverApiOrNull<T>(path: string): Promise<T | null> {
  try {
    return await serverApi<T>(path);
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ */
/* Paylaşılan yanıt tipleri (FastAPI sözleşmesinin istemci karşılığı)   */
/* ------------------------------------------------------------------ */

export interface MeResponse {
  staff: { id: number; name: string; role: string; branchId: number; photoUrl: string | null } | null;
  customer: {
    id: number;
    firstName: string;
    lastName: string | null;
    phone: string;
    tier: string;
    loyaltyPoints: number;
    engagementOptIn: boolean;
  } | null;
  welcome: {
    firstName: string;
    headline: string;
    subline: string | null;
    isDue: boolean;
    repeatServiceIds: number[];
    lastVisit: { date: string; dateLabel: string; serviceNames: string[]; daysAgo: number } | null;
    tierProgress: {
      current: string;
      next: string | null;
      pointsToNext: number;
      ratio: number;
      message: string;
    };
    upcoming: {
      id: number;
      date: string;
      dateLabel: string;
      startMin: number;
      serviceNames: string[];
      staffName: string;
    } | null;
  } | null;
}

export interface SalonInfo {
  branchId: number;
  salonName: string;
  branchName: string;
  phone: string | null;
  address: string | null;
  openMinute: number;
  closeMinute: number;
}

export interface PublicReview {
  id: number;
  authorName: string;
  rating: number;
  comment: string;
  serviceNames: string | null;
  staffName: string | null;
  isVerified: boolean;
  createdAt: string;
  reply: string | null;
}

export interface ReviewSummary {
  count: number;
  average: number | null;
  distribution: Record<string, number>;
  positiveRate: number;
}
