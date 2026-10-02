import { adminApi } from '@/lib/admin-api';
import type { MeResponse } from '@/lib/server-api';
import { WelcomeSettings, type WelcomeSettingsData } from './welcome-settings';
import { WhatsappConnect, type MessagingStatus } from './whatsapp-connect';

export const dynamic = 'force-dynamic';

/**
 * ====================================================================
 * WHATSAPP BAĞLANTISI
 * ====================================================================
 *
 * OTP kodları ve randevu hatırlatmaları salonun WhatsApp numarasından
 * (Evolution API, QR ile bağlı numara) gönderilir. Bu sayfa bağlantı
 * durumunu gösterir; salon sahibi (OWNER) buradan QR okutarak numarayı
 * bağlar veya bağlantıyı keser. Yönetici (MANAGER) yalnızca durumu görür.
 * İlk kez yazan kişiye giden karşılama mesajını yönetici ve sahip düzenler.
 */
export default async function WhatsappPage() {
  const me = await adminApi<MeResponse>('/api/me');
  const role = me.staff?.role ?? 'STAFF';

  if (role === 'STAFF') {
    return (
      <div className="card !p-4">
        <p className="muted">Bu bölümü yalnızca yönetici ve salon sahibi görebilir.</p>
      </div>
    );
  }

  const [status, welcome] = await Promise.all([
    adminApi<MessagingStatus>('/api/admin/messaging/status'),
    adminApi<WelcomeSettingsData>('/api/admin/messaging/welcome'),
  ]);

  return (
    <div className="space-y-3">
      <p className="muted">
        Doğrulama kodları ve randevu hatırlatmaları bu numaradan gönderilir.
      </p>

      <WhatsappConnect initialStatus={status} canManage={role === 'OWNER'} />

      {status.driver === 'evolution' && <WelcomeSettings initial={welcome} />}

      <section className="card space-y-2 !p-4 text-sm">
        <h2 className="eyebrow">Dikkat edilmesi gerekenler</h2>
        <ul className="list-disc space-y-1 pl-5 text-xs text-ink-700">
          <li>
            Salonun ana numarasını değil, <strong>ayrı bir numara</strong> kullanın. QR ile bağlantı
            resmi bir entegrasyon değildir; WhatsApp numarayı kısıtlayabilir.
          </li>
          <li>
            Bu numaradan yalnızca doğrulama kodu ve randevu hatırlatması gönderilir; toplu kampanya
            mesajı gönderilmez.
          </li>
          <li>
            Telefon uzun süre internetsiz kalırsa veya &quot;Bağlı cihazlar&quot; listesinden
            kaldırılırsa bağlantı düşer. Durum &quot;Bağlı&quot; değilse müşteriler giriş kodu
            alamaz; QR kodunu yeniden okutun.
          </li>
        </ul>
      </section>
    </div>
  );
}
