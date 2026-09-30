import { redirect } from 'next/navigation';

import { serverApi, type MeResponse } from '@/lib/server-api';
import { StaffLoginForm } from './staff-login-form';

export const dynamic = 'force-dynamic';

/**
 * Personel girişi.
 *
 * Bu sayfa BİLEREK `(panel)` route grubunun DIŞINDADIR: panel layout'u
 * `requireStaff` ile korunuyor, giriş sayfası da orada olsaydı sonsuz
 * yönlendirme döngüsü oluşurdu.
 */
export default async function StaffLoginPage() {
  const me = await serverApi<MeResponse>('/api/me');
  if (me.staff) redirect('/admin');

  return (
    <div className="mx-auto flex min-h-dvh max-w-md flex-col justify-center gap-4 p-4">
      <div className="text-center">
        <h1 className="text-2xl font-semibold">Personel Paneli</h1>
        <p className="mt-2 muted">Telefon numaran ve şifrenle giriş yap.</p>
      </div>

      <StaffLoginForm />

      <p className="text-center text-xs text-ink-500">
        Demo: <strong>05551110001</strong> / <strong>admin123</strong>
      </p>
    </div>
  );
}
