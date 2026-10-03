import { adminApi } from '@/lib/admin-api';
import type { MeResponse } from '@/lib/server-api';
import { DepositSettings, type DepositSettingsData } from './deposit-settings';
import { PostVisitSettings, type PostVisitSettingsData } from './post-visit-settings';
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

  const [status, welcome, postVisit, depositSettings] = await Promise.all([
    adminApi<MessagingStatus>('/api/admin/messaging/status'),
    adminApi<WelcomeSettingsData>('/api/admin/messaging/welcome'),
    adminApi<PostVisitSettingsData>('/api/admin/messaging/post-visit'),
    adminApi<DepositSettingsData>('/api/admin/settings/deposit'),
  ]);

  return (
    <div className="space-y-3">
      <p className="muted">
        Doğrulama kodları ve randevu hatırlatmaları bu numaradan gönderilir.
      </p>

      <WhatsappConnect initialStatus={status} canManage={role === 'OWNER'} />

      {status.driver === 'evolution' && <WelcomeSettings initial={welcome} />}
      {status.driver === 'evolution' && <PostVisitSettings initial={postVisit} />}
      <DepositSettings initial={depositSettings} />
    </div>
  );
}
