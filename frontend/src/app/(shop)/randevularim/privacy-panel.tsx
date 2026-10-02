'use client';

import { Download, TriangleAlert } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { ApiError, apiGet, apiSend } from '@/lib/api-client';

export interface PrivacyStatus {
  marketingConsent: boolean;
  marketingConsentAt: string | null;
  healthConsent: boolean;
  healthConsentAt: string | null;
  hasHealthData: boolean;
}

function formatDate(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString('tr-TR') : '';
}

/**
 * KVKK m.11 hakları için self-servis bölüm: ileti onayı, sağlık verisi
 * rızasının geri alınması, verilerin indirilmesi ve hesabın silinmesi.
 * Kurallar sunucuda (`/api/me/privacy`, `/api/me/export`, `DELETE /api/me`).
 */
export function PrivacyPanel({ initial }: { initial: PrivacyStatus }) {
  const router = useRouter();
  const [status, setStatus] = useState(initial);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<'health' | 'delete' | null>(null);

  async function act(key: string, fn: () => Promise<void>) {
    setBusy(key);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'İşlem başarısız. Lütfen tekrar dene.');
    } finally {
      setBusy(null);
      setConfirm(null);
    }
  }

  const toggleMarketing = () =>
    act('marketing', async () => {
      setStatus(
        await apiSend<PrivacyStatus>('/api/me/privacy', 'PATCH', {
          marketingConsent: !status.marketingConsent,
        }),
      );
    });

  const withdrawHealth = () =>
    act('health', async () => {
      setStatus(
        await apiSend<PrivacyStatus>('/api/me/privacy', 'PATCH', { healthConsent: false }),
      );
    });

  const download = () =>
    act('export', async () => {
      const data = await apiGet<unknown>('/api/me/export');
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `verilerim-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    });

  const deleteAccount = () =>
    act('delete', async () => {
      await apiSend('/api/me', 'DELETE');
      router.push('/');
      router.refresh();
    });

  return (
    <section id="gizlilik" className="scroll-mt-24 space-y-4">
      <div>
        <p className="eyebrow">Gizlilik</p>
        <h2 className="section-title mt-1">Gizlilik ve verilerim</h2>
      </div>

      <div className="card divide-y divide-sand-200 p-0 md:p-0">
        {/* Ticari ileti onayı */}
        <div className="flex items-start justify-between gap-4 p-5">
          <div>
            <p className="text-sm font-medium">Hatırlatma ve kampanya iletileri</p>
            <p className="muted mt-0.5">
              {status.marketingConsent
                ? `WhatsApp ile bakım hatırlatması alıyorsun (onay: ${formatDate(status.marketingConsentAt)}).`
                : 'Bakım zamanı hatırlatması ve kampanya iletisi almıyorsun.'}{' '}
              Randevu hatırlatmaları bundan bağımsızdır.{' '}
              <Link href="/acik-riza#ticari-ileti" className="underline underline-offset-2">
                Onay metni
              </Link>
            </p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={status.marketingConsent}
            aria-label="Hatırlatma ve kampanya iletileri"
            disabled={busy === 'marketing'}
            onClick={() => void toggleMarketing()}
            className={`relative mt-1 h-7 w-12 shrink-0 rounded-full transition focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum-600 ${
              status.marketingConsent ? 'bg-plum-600' : 'bg-sand-300'
            }`}
          >
            <span
              className={`absolute top-1 h-5 w-5 rounded-full bg-white transition-all ${
                status.marketingConsent ? 'left-6' : 'left-1'
              }`}
            />
          </button>
        </div>

        {/* Sağlık verisi */}
        <div className="p-5">
          <p className="text-sm font-medium">Alerji bilgisi (sağlık verisi)</p>
          {status.healthConsent ? (
            <>
              <p className="muted mt-0.5">
                {formatDate(status.healthConsentAt)} tarihinde verdiğin açık rızayla salonda alerji
                bilgin kayıtlı; usta işlem öncesi uyarı görür.
              </p>
              {confirm === 'health' ? (
                <div className="alert alert-warning mt-3 block">
                  <p>
                    Kayıtlı alerji bilgilerin <strong>kalıcı olarak silinecek</strong>. Sonraki
                    ziyaretlerinde alerjini ustana sözlü olarak bildirmelisin.
                  </p>
                  <div className="mt-3 flex gap-2">
                    <button type="button" className="btn-secondary btn-sm flex-1" onClick={() => setConfirm(null)}>
                      Vazgeç
                    </button>
                    <button
                      type="button"
                      className="btn-secondary btn-sm flex-1 border-warning-600 text-warning-600 hover:bg-warning-600 hover:text-white"
                      disabled={busy === 'health'}
                      onClick={() => void withdrawHealth()}
                    >
                      Rızamı geri al
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  className="btn-link mt-3 text-warning-600 hover:text-warning-600"
                  onClick={() => setConfirm('health')}
                >
                  Rızamı geri al ve bilgileri sil
                </button>
              )}
            </>
          ) : (
            <p className="muted mt-0.5">
              Kayıtlı sağlık bilgin yok. Alerjin varsa salonda personelimize bildirebilirsin.
            </p>
          )}
        </div>

        {/* Verilerimi indir */}
        <div className="flex items-center justify-between gap-4 p-5">
          <div>
            <p className="text-sm font-medium">Verilerimi indir</p>
            <p className="muted mt-0.5">Hakkında tuttuğumuz bilgilerin bir kopyası (JSON).</p>
          </div>
          <button
            type="button"
            className="btn-secondary btn-sm shrink-0"
            disabled={busy === 'export'}
            onClick={() => void download()}
          >
            <Download size={16} strokeWidth={1.5} aria-hidden />
            {busy === 'export' ? 'Hazırlanıyor…' : 'İndir'}
          </button>
        </div>

        {/* Hesabımı sil */}
        <div className="p-5">
          <p className="text-sm font-medium">Hesabımı sil</p>
          {confirm === 'delete' ? (
            <div className="alert alert-danger mt-3 block">
              <p>
                Adın, telefonun, alerji bilgilerin, fotoğrafların, yorumların ve sadakat puanların{' '}
                <strong>kalıcı olarak silinir</strong>. Bu işlem geri alınamaz. Geçmiş randevuların
                yalnızca kimliksiz istatistik olarak kalır.
              </p>
              <div className="mt-3 flex gap-2">
                <button type="button" className="btn-secondary btn-sm flex-1" onClick={() => setConfirm(null)}>
                  Vazgeç
                </button>
                <button
                  type="button"
                  className="btn-danger btn-sm flex-1"
                  disabled={busy === 'delete'}
                  onClick={() => void deleteAccount()}
                >
                  {busy === 'delete' ? 'Siliniyor…' : 'Evet, kalıcı olarak sil'}
                </button>
              </div>
            </div>
          ) : (
            <>
              <p className="muted mt-0.5">Yaklaşan randevun varsa önce iptal etmelisin.</p>
              <button
                type="button"
                className="btn-link mt-3 text-danger-600 hover:text-danger-700"
                onClick={() => setConfirm('delete')}
              >
                Hesabımı sil
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" role="alert">
          <TriangleAlert size={16} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
          <p>{error}</p>
        </div>
      )}
      <p className="muted">
        Diğer talepler için{' '}
        <Link href="/kvkk#basvuru" className="underline underline-offset-2">
          KVKK başvuru yöntemi
        </Link>
        .
      </p>
    </section>
  );
}
