import { redirect } from 'next/navigation';

import { serverApi, type MeResponse } from '@/lib/server-api';
import { LoginForm } from './login-form';

export const dynamic = 'force-dynamic';

/**
 * `next` yalnızca site içi bir yol olabilir. Aksi halde
 * `/giris?next=https://kotu.site` gibi bir bağlantı, girişten sonra
 * kullanıcıyı dış bir siteye yönlendirirdi (açık yönlendirme).
 */
function safeNext(next: string | undefined): string {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) {
    return '/hesabim';
  }
  return next;
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const [me, { next }] = await Promise.all([
    serverApi<MeResponse>('/api/me'),
    searchParams,
  ]);

  const nextUrl = safeNext(next);
  if (me.customer) redirect(nextUrl);

  return (
    <div className="mx-auto max-w-md space-y-4 px-4 py-8">
      <div className="text-center">
        <h1 className="text-2xl font-semibold">Üye Girişi</h1>
        <p className="mt-2 muted">
          Şifre yok — telefonuna gelen 6 haneli kodla giriş yaparsın.
        </p>
      </div>

      <LoginForm nextUrl={nextUrl} />

      <div className="card bg-sand-100">
        <h2 className="text-sm font-semibold">Neden üyelik gerekiyor?</h2>
        <ul className="mt-2 space-y-1 text-sm text-ink-700">
          <li>• Randevunu iptal edebilmen ve geçmişini görebilmen için</li>
          <li>• Ustanın alerji/tercih notlarını doğru kişiye bağlayabilmek için</li>
          <li>• Sadakat puanlarının birikmesi için</li>
        </ul>
        <p className="mt-2 muted">
          Hizmetleri ve uygun saatleri üye olmadan da inceleyebilirsin.
        </p>
      </div>
    </div>
  );
}
