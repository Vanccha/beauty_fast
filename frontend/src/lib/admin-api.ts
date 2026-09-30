import { redirect } from 'next/navigation';

import { ApiError, serverApi } from '@/lib/server-api';

/**
 * Panel sayfaları için `serverApi` sarmalayıcısı.
 *
 * Yetki kapısı `(panel)/layout.tsx` içindedir; ancak Next.js düzen ve
 * sayfayı paralel işleyebildiği için oturum düşmüşse sayfanın kendi
 * isteği de `UNAUTHORIZED` ile dönebilir. Bu durumda hata sayfası yerine
 * düzenle aynı davranış uygulanır: giriş ekranına yönlendirilir.
 */
export async function adminApi<T>(path: string): Promise<T> {
  try {
    return await serverApi<T>(path);
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.code === 'UNAUTHORIZED')) {
      redirect('/admin/giris');
    }
    throw e;
  }
}
