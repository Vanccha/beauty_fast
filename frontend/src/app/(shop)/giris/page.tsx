import { redirect } from 'next/navigation';

import { safeNext } from '@/lib/safe-next';

export const dynamic = 'force-dynamic';

/** Eski giriş bağlantıları → Randevu Sorgula (güvenli `next` korunur). */
export default async function LoginRedirect({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;
  const safe = safeNext(next);
  redirect(safe ? `/randevularim?next=${encodeURIComponent(safe)}` : '/randevularim');
}
