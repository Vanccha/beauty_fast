import { redirect } from 'next/navigation';

import { serverApi, type MeResponse, type SalonInfo } from '@/lib/server-api';
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
  const [me, showcase] = await Promise.all([
    serverApi<MeResponse>('/api/me'),
    serverApi<{ salon: SalonInfo }>('/api/showcase'),
  ]);
  if (me.staff) redirect('/admin');

  return (
    <div className="mx-auto flex min-h-dvh max-w-sm flex-col justify-center gap-6 px-4 py-8">
      <div className="text-center">
        <p className="eyebrow">Personel paneli</p>
        <h1 className="display mt-2 text-3xl leading-tight text-ink-900">
          {showcase.salon.salonName}
        </h1>
        <p className="muted mt-2">Telefon numaranız ve şifrenizle giriş yapın.</p>
      </div>

      <StaffLoginForm />

      <p className="text-center text-xs text-ink-400">
        Demo: <strong>05551110001</strong> / <strong>admin123</strong>
      </p>
    </div>
  );
}
