'use client';

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
    <section id="gizlilik" className="scroll-mt-24 space-y-2">
      <h2 className="section-title">Gizlilik ve verilerim</h2>

      <div className="card divide-y divide-sand-100 p-0">
        {/* Ticari ileti onayı */}
        <div className="flex items-start justify-between gap-4 p-4">
          <div>
            <p className="text-sm font-medium">Hatırlatma ve kampanya iletileri</p>
            <p className="muted mt-0.5">
              {status.marketingConsent
                ? `WhatsApp ile bakım hatırlatması alıyorsun (onay: ${formatDate(status.marketingConsentAt)}).`
                : 'Bakım zamanı hatırlatması ve kampanya iletisi almıyorsun.'}{' '}
              Randevu hatırlatmaları bundan bağımsızdır.{' '}
              <Link href="/acik-riza#ticari-ileti" className="underline">
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
            className={`relative mt-1 h-7 w-12 shrink-0 rounded-full transition ${
              status.marketingConsent ? 'bg-plum-600' : 'bg-sand-300'
            }`}
          >
            <span
              className={`absolute top-1 h-5 w-5 rounded-full bg-white shadow transition-all ${
                status.marketingConsent ? 'left-6' : 'left-1'
              }`}
            />
          </button>
        </div>

        {/* Sağlık verisi */}
        <div className="p-4">
          <p className="text-sm font-medium">Alerji bilgisi (sağlık verisi)</p>
          {status.healthConsent ? (
            <>
              <p className="muted mt-0.5">
                {formatDate(status.healthConsentAt)} tarihinde verdiğin açık rızayla salonda alerji
                bilgin kayıtlı; usta işlem öncesi uyarı görür.
              </p>
              {confirm === 'health' ? (
                <div className="mt-3 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
                  <p>
                    Kayıtlı alerji bilgilerin <strong>kalıcı olarak silinecek</strong>. Sonraki
                    ziyaretlerinde alerjini ustana sözlü olarak bildirmelisin.
                  </p>
                  <div className="mt-3 flex gap-2">
                    <button type="button" className="btn-secondary flex-1" onClick={() => setConfirm(null)}>
                      Vazgeç
                    </button>
                    <button
                      type="button"
                      className="btn flex-1 bg-amber-600 text-white hover:bg-amber-700"
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
                  className="btn-ghost mt-2 px-0 text-sm text-amber-700"
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
        <div className="flex items-center justify-between gap-4 p-4">
          <div>
            <p className="text-sm font-medium">Verilerimi indir</p>
            <p className="muted mt-0.5">Hakkında tuttuğumuz bilgilerin bir kopyası (JSON).</p>
          </div>
          <button
            type="button"
            className="btn-secondary shrink-0 text-sm"
            disabled={busy === 'export'}
            onClick={() => void download()}
          >
            {busy === 'export' ? 'Hazırlanıyor…' : 'İndir'}
          </button>
        </div>

        {/* Hesabımı sil */}
        <div className="p-4">
          <p className="text-sm font-medium">Hesabımı sil</p>
          {confirm === 'delete' ? (
            <div className="mt-2 rounded-xl bg-rose-50 p-3 text-sm text-rose-900">
              <p>
                Adın, telefonun, alerji bilgilerin, fotoğrafların, yorumların ve sadakat puanların{' '}
                <strong>kalıcı olarak silinir</strong>. Bu işlem geri alınamaz. Geçmiş randevuların
                yalnızca kimliksiz istatistik olarak kalır.
              </p>
              <div className="mt-3 flex gap-2">
                <button type="button" className="btn-secondary flex-1" onClick={() => setConfirm(null)}>
                  Vazgeç
                </button>
                <button
                  type="button"
                  className="btn flex-1 bg-rose-600 text-white hover:bg-rose-700"
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
                className="btn-ghost mt-2 px-0 text-sm text-rose-600"
                onClick={() => setConfirm('delete')}
              >
                Hesabımı sil
              </button>
            </>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}
      <p className="muted">
        Diğer talepler için{' '}
        <Link href="/kvkk#basvuru" className="underline">
          KVKK başvuru yöntemi
        </Link>
        .
      </p>
    </section>
  );
}
