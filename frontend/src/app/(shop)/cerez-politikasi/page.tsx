import type { Metadata } from 'next';
import Link from 'next/link';

import { LegalDocument } from '@/components/legal/LegalDocument';
import { RETENTION } from '@/lib/legal';

export const metadata: Metadata = { title: 'Çerez Politikası' };

/**
 * Sitede YALNIZCA zorunlu çerezler ve tarayıcı depolaması kullanılır;
 * analitik/reklam çerezi yoktur. Bu yüzden çerez onay penceresi
 * gösterilmez (zorunlu çerezler rızadan muaftır). İleride analitik veya
 * reklam aracı eklenirse ÖNCE onay penceresi eklenmeli ve bu tablo
 * güncellenmelidir.
 *
 * Kaynaklar: backend `app/auth/sessions.py` (çerezler), arayüz
 * `components/pwa/InstallBanner.tsx` (localStorage), `public/sw.js`.
 */
export default function CookiePolicyPage() {
  return (
    <LegalDocument title="Çerez Politikası">
      <p>
        Bu sayfa, sitemizde ve mobil uygulamamızda kullanılan çerezleri ve benzeri tarayıcı
        depolama teknolojilerini açıklar. Kişisel verilerinizin işlenmesine ilişkin genel bilgi
        için <Link href="/kvkk">KVKK Aydınlatma Metni</Link>&apos;ni inceleyebilirsiniz.
      </p>

      <h2>Hangi çerezleri kullanıyoruz?</h2>
      <p>
        Sitemizde <strong>yalnızca sitenin çalışması için zorunlu</strong> çerezler kullanılır.
        Reklam, pazarlama veya ziyaretçi analitiği (ör. Google Analytics) çerezi kullanılmaz ve
        verileriniz bu amaçlarla üçüncü taraflarla paylaşılmaz. Zorunlu çerezler için onayınız
        gerekmez; ancak bunları tarayıcınızdan engellerseniz giriş ve randevu işlemleri
        çalışmaz.
      </p>

      <div className="overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Ad</th>
              <th>Tür</th>
              <th>Amaç</th>
              <th>Süre</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>
                <code>customer_session</code>
              </td>
              <td>Zorunlu çerez</td>
              <td>Üye girişinizi açık tutar</td>
              <td>{RETENTION.customerSessionDays} gün veya çıkışa kadar</td>
            </tr>
            <tr>
              <td>
                <code>staff_session</code>
              </td>
              <td>Zorunlu çerez</td>
              <td>Yalnızca salon personelinin panel girişi</td>
              <td>{RETENTION.staffSessionDays} gün veya çıkışa kadar</td>
            </tr>
            <tr>
              <td>
                <code>visitor_key</code>
              </td>
              <td>Zorunlu çerez</td>
              <td>
                Randevu sırasında seçtiğiniz saatin birkaç dakikalığına sizin için ayrılması ve
                aynı saate bakan kişi sayısının doğru gösterilmesi. Rastgele bir değerdir, sizi
                kişisel olarak tanımlamaz.
              </td>
              <td>{RETENTION.visitorKeyDays} gün</td>
            </tr>
            <tr>
              <td>
                <code>aurora:install-dismissed-at</code>
              </td>
              <td>Tarayıcı depolaması (localStorage)</td>
              <td>&quot;Ana ekrana ekle&quot; önerisini kapattığınızı hatırlar</td>
              <td>30 gün sonra öneri yeniden gösterilebilir</td>
            </tr>
            <tr>
              <td>Uygulama önbelleği</td>
              <td>Service worker önbelleği</td>
              <td>
                Uygulamanın hızlı açılması ve bağlantı yokken temel sayfaların görüntülenmesi.
                Kişisel sayfalar (Hesabım, randevu, giriş) önbelleğe alınmaz.
              </td>
              <td>Uygulama güncellenene kadar</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2>Çerezleri nasıl silebilirim?</h2>
      <p>
        Tarayıcınızın ayarlarından bu siteye ait çerezleri ve site verilerini dilediğiniz zaman
        silebilirsiniz. Ana ekrana eklediğiniz uygulamayı kaldırmanız da uygulama önbelleğini
        temizler.
      </p>
    </LegalDocument>
  );
}
