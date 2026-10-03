/**
 * İstemci tarafı API yardımcısı.
 *
 * Tüm route'lar `{ ok, data } | { ok:false, error }` sözleşmesini kullanır.
 * Bu sarmalayıcı hatayı `ApiError`'a çevirir, böylece bileşenler
 * `try/catch` ile tek biçimde çalışır ve `error.code` üzerinden özel
 * davranış tanımlayabilir (`MEMBERSHIP_REQUIRED` → giriş modalı,
 * `SLOT_TAKEN` → slot ızgarasını tazele).
 */

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status: number,
    public details?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

async function unwrap<T>(response: Response): Promise<T> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError('INTERNAL', 'Sunucu yanıtı okunamadı.', response.status);
  }

  const body = payload as
    | { ok: true; data: T }
    | { ok: false; error: { code: string; message: string; details?: unknown } };

  if (!body || typeof body !== 'object' || !('ok' in body)) {
    throw new ApiError('INTERNAL', 'Beklenmeyen sunucu yanıtı.', response.status);
  }

  if (!body.ok) {
    throw new ApiError(body.error.code, body.error.message, response.status, body.error.details);
  }

  return body.data;
}

export async function apiGet<T>(url: string): Promise<T> {
  return unwrap<T>(await fetch(url, { cache: 'no-store' }));
}

export async function apiSend<T>(
  url: string,
  method: 'POST' | 'PATCH' | 'PUT' | 'DELETE',
  body?: unknown,
): Promise<T> {
  return unwrap<T>(
    await fetch(url, {
      method,
      headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  );
}

/** `multipart/form-data` gönderimi — Content-Type tarayıcıya bırakılır. */
export async function apiUpload<T>(
  url: string,
  form: FormData,
  method: 'POST' | 'PATCH' = 'POST',
): Promise<T> {
  return unwrap<T>(await fetch(url, { method, body: form }));
}

/** 570 → "09:30" (istemci tarafında da gerekiyor) */
export function timeLabel(minute: number): string {
  const h = Math.floor(minute / 60);
  const m = minute % 60;
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

export function formatTl(value: number): string {
  return new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
    maximumFractionDigits: 0,
  }).format(value);
}

/** 110 → "1 sa 50 dk" */
export function durationLabel(minutes: number): string {
  if (minutes < 60) return `${minutes} dk`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m === 0 ? `${h} sa` : `${h} sa ${m} dk`;
}
