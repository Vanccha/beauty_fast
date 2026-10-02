import type { Metadata } from 'next';
import Link from 'next/link';

import { ControllerCard, LegalDocument } from '@/components/legal/LegalDocument';
import { LEGAL, RETENTION } from '@/lib/legal';
import { serverApi, type SalonInfo } from '@/lib/server-api';

export const metadata: Metadata = { title: 'KVKK Aydınlatma Metni' };

/**
 * KVKK m.10 aydınlatma yükümlülüğü.
 *
 * İçerik sistemin GERÇEKTE işlediği verilere göre yazıldı (backend
 * `app/models.py`). Yeni bir kişisel veri alanı eklenirse bu metin de
 * güncellenmeli. Saklama süreleri `@/lib/legal` → `RETENTION`.
 */
export default async function KvkkPage() {
  const { salon } = await serverApi<{ salon: SalonInfo }>('/api/showcase');

  return (
    <LegalDocument title="Kişisel Verilerin Korunması Aydınlatma Metni">
      <p>
        {salon.salonName} olarak kişisel verilerinizin güvenliğine önem veriyoruz. Bu metin, 6698
        sayılı Kişisel Verilerin Korunması Kanunu (&quot;KVKK&quot;) madde 10 uyarınca; web sitemiz,
        mobil uygulamamız ve salonumuz üzerinden randevu ve hizmet süreçlerinde hangi kişisel
        verilerinizi, hangi amaçlarla ve hangi hukuki sebeplerle işlediğimizi açıklar.
      </p>

      <h2 id="sorumlu">1. Veri sorumlusu</h2>
      <ControllerCard salonName={salon.salonName} address={salon.address} phone={salon.phone} />

      <h2 id="veriler">2. İşlenen kişisel veriler, amaçlar ve hukuki sebepler</h2>
      <div className="overflow-x-auto">
        <table>
          <thead>
            <tr>
              <th>Veri kategorisi</th>
              <th>Hangi veriler</th>
              <th>Amaç</th>
              <th>Hukuki sebep (KVKK)</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Kimlik</td>
              <td>Ad, soyad</td>
              <td>Üyelik, randevu oluşturma, sizi salonda tanıma</td>
              <td>m.5/2-c sözleşmenin kurulması ve ifası</td>
            </tr>
            <tr>
              <td>İletişim</td>
              <td>Cep telefonu, e-posta (verirseniz)</td>
              <td>
                Telefonla giriş (doğrulama kodu), randevu onayı ve randevu öncesi hatırlatma,
                randevu değişikliğinde size ulaşma
              </td>
              <td>m.5/2-c sözleşmenin kurulması ve ifası</td>
            </tr>
            <tr>
              <td>Müşteri işlem</td>
              <td>
                Randevu tarihleri, alınan hizmetler, ustanız, tutarlar, indirimler, sadakat puanı
                ve seviyesi, kampanya kullanımları, randevuya eklediğiniz tasarım referansları
              </td>
              <td>
                Randevunun planlanması ve yürütülmesi, sadakat programı, size uygun kampanyaların
                uygulanması, salon doluluk istatistikleri
              </td>
              <td>
                m.5/2-c sözleşmenin ifası; mali kayıtlar için m.5/2-ç hukuki yükümlülük;
                istatistik için m.5/2-f meşru menfaat
              </td>
            </tr>
            <tr>
              <td>Doğum tarihi</td>
              <td>Gün/ay/yıl (yalnızca siz paylaşırsanız)</td>
              <td>Doğum günü indirimi</td>
              <td>m.5/2-f meşru menfaat</td>
            </tr>
            <tr>
              <td>Görsel kayıt</td>
              <td>İşlem öncesi/sonrası fotoğraflar, renk ve ürün bilgisi</td>
              <td>
                Uygulanan renk ve işlemin kaydı; bir sonraki seansta aynı sonucun elde edilmesi.
                Bu fotoğraflar yalnızca salon personeli ve Randevu Sorgula sayfanızda size görünür;
                tanıtımda kullanılmaz.
              </td>
              <td>m.5/2-c sözleşmenin ifası, m.5/2-f meşru menfaat</td>
            </tr>
            <tr>
              <td>
                <strong>Sağlık verisi</strong> (özel nitelikli)
              </td>
              <td>Alerji ve hassasiyet bilgisi (örn. boya veya lateks alerjisi)</td>
              <td>İşlem sırasında sağlığınızın korunması; usta işleme başlamadan uyarı görür</td>
              <td>
                m.6/3 <strong>açık rızanız</strong> —{' '}
                <Link href="/acik-riza#saglik">Açık Rıza Metni</Link>
              </td>
            </tr>
            <tr>
              <td>Müşteri yorumu</td>
              <td>Puan, yorum metni, adınız ve soyadınızın baş harfi</td>
              <td>Hizmet kalitesinin ölçülmesi; yorumun sitede yayınlanması</td>
              <td>
                Yorumu yayınlanmak üzere kendiniz yazdığınız için m.5/2-d (ilgili kişinin
                alenileştirmesi)
              </td>
            </tr>
            <tr>
              <td>Randevu güvenilirliği</td>
              <td>
                Telefon numaranızın geri döndürülemez şekilde şifrelenmiş (hash) hali ile
                randevuya gelip gelmediğiniz bilgisi
              </td>
              <td>
                Sık iptal veya habersiz gelmeme durumlarının tespiti; randevu saatlerinin
                kötüye kullanılmasının önlenmesi
              </td>
              <td>m.5/2-f meşru menfaat</td>
            </tr>
            <tr>
              <td>Ticari ileti</td>
              <td>Telefon, ad, son aldığınız hizmet</td>
              <td>
                &quot;Bakım zamanınız geldi&quot; türünden tekrar hatırlatmaları ve kampanya
                bildirimleri
              </td>
              <td>
                <strong>Onay vermeniz halinde</strong> (6563 sayılı Kanun ve m.5/1) —{' '}
                <Link href="/acik-riza#ticari-ileti">Onay Metni</Link>
              </td>
            </tr>
            <tr>
              <td>İşlem güvenliği</td>
              <td>
                IP adresi, oturum ve tarayıcı tanımlayıcı çerezleri, doğrulama kodu deneme kayıtları
              </td>
              <td>
                Hesabınızın güvenliği, kaba kuvvet ve kötüye kullanım girişimlerinin
                engellenmesi
              </td>
              <td>m.5/2-f meşru menfaat, m.5/2-ç hukuki yükümlülük (5651 sayılı Kanun)</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2 id="yontem">3. Toplama yöntemi</h2>
      <p>
        Kişisel verileriniz; web sitemiz ve mobil uygulamamızdaki giriş ve randevu formları,
        Randevu Sorgula sayfası, WhatsApp üzerinden yürütülen yazışmalar ve salonda personelimiz
        tarafından müşteri kartınıza yapılan kayıtlar aracılığıyla, kısmen otomatik (site ve
        uygulama) ve kısmen otomatik olmayan yollarla (salonda sözlü beyanınız) toplanır.
      </p>

      <h2 id="aktarim">4. Kişisel verilerin aktarılması</h2>
      <ul>
        <li>
          <strong>Mesajlaşma hizmeti:</strong> Doğrulama kodları ve hatırlatmalar WhatsApp
          üzerinden gönderilir. Bu nedenle telefon numaranız ve mesaj içeriği, WhatsApp hizmet
          sağlayıcısının yurt dışındaki sunucularında işlenebilir. Bu aktarım KVKK m.9 kapsamında
          gerçekleştirilir.
        </li>
        <li>
          <strong>Barındırma hizmeti:</strong> Sistemimizin çalıştığı sunucu ve veritabanı
          hizmetini aldığımız sağlayıcı, verileri yalnızca bizim adımıza ve talimatımızla
          (veri işleyen sıfatıyla) saklar.
        </li>
        <li>
          <strong>Randevu güvenilirliği havuzu:</strong> Yalnızca şifrelenmiş (hash) telefon
          değeri ve gelme/gelmeme bilgisi, sistemi kullanan diğer salonlarla ortak bir havuzda
          değerlendirilir. Diğer salonlar adınızı, numaranızı veya hangi salonda ne olduğunu
          göremez; yalnızca toplu bir güvenilirlik puanı oluşur.
        </li>
        <li>
          <strong>Yetkili kurumlar:</strong> Kanunen talep edilmesi halinde yargı mercileri ve
          yetkili kamu kurum ve kuruluşları.
        </li>
      </ul>
      <p>Kişisel verileriniz pazarlama amacıyla üçüncü kişilere satılmaz veya kiralanmaz.</p>

      <h2 id="saklama">5. Saklama süreleri</h2>
      <div className="overflow-x-auto">
        <table>
          <tbody>
            <tr>
              <td>Üyelik, randevu ve işlem kayıtları</td>
              <td>
                Üyeliğiniz sürdükçe. Hesabınızı sildiğinizde kimliğinizi belirleyen bilgiler
                silinir; randevu kayıtları kimliksiz istatistik olarak kalır.
              </td>
            </tr>
            <tr>
              <td>Alerji bilgisi</td>
              <td>Açık rızanızı geri alana veya hesabınızı silene kadar</td>
            </tr>
            <tr>
              <td>Doğrulama kodları</td>
              <td>{RETENTION.otpMinutes} dakika geçerli; süresi dolunca silinir</td>
            </tr>
            <tr>
              <td>Oturum</td>
              <td>{RETENTION.customerSessionDays} gün ya da çıkış yapana kadar</td>
            </tr>
            <tr>
              <td>Gönderilmiş bildirim kayıtları</td>
              <td>{RETENTION.notificationDays} gün</td>
            </tr>
            <tr>
              <td>Randevu güvenilirliği kayıtları</td>
              <td>{RETENTION.riskEventMonths} ay</td>
            </tr>
            <tr>
              <td>Saat görüntüleme sayaçları</td>
              <td>{RETENTION.slotViewDays} gün</td>
            </tr>
            <tr>
              <td>Mali kayıtlar</td>
              <td>İlgili mevzuatta (Vergi Usul Kanunu, Türk Ticaret Kanunu) öngörülen süre</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p>
        Süresi dolan veriler sistem tarafından düzenli olarak otomatik silinir veya anonim hale
        getirilir.
      </p>

      <h2 id="haklar">6. KVKK madde 11 kapsamındaki haklarınız</h2>
      <p>Veri sorumlusuna başvurarak:</p>
      <ol>
        <li>Kişisel verilerinizin işlenip işlenmediğini öğrenme,</li>
        <li>İşlenmişse buna ilişkin bilgi talep etme,</li>
        <li>İşlenme amacını ve amacına uygun kullanılıp kullanılmadığını öğrenme,</li>
        <li>Yurt içinde veya yurt dışında aktarıldığı üçüncü kişileri bilme,</li>
        <li>Eksik veya yanlış işlenmişse düzeltilmesini isteme,</li>
        <li>KVKK m.7 çerçevesinde silinmesini veya yok edilmesini isteme,</li>
        <li>
          Düzeltme, silme ve yok etme işlemlerinin verilerin aktarıldığı üçüncü kişilere
          bildirilmesini isteme,
        </li>
        <li>
          Münhasıran otomatik sistemlerle analiz edilmesi sonucu aleyhinize bir sonucun ortaya
          çıkmasına itiraz etme,
        </li>
        <li>Kanuna aykırı işleme nedeniyle zarara uğramanız halinde zararın giderilmesini talep etme</li>
      </ol>
      <p>haklarına sahipsiniz.</p>

      <h2 id="basvuru">7. Başvuru yöntemi</h2>
      <p>
        <strong>Hızlı yol:</strong> Üyeyseniz{' '}
        <Link href="/randevularim#gizlilik">Randevu Sorgula → Kişisel verilerim ve verilerim</Link> bölümünden
        verilerinizi indirebilir, ileti onayınızı ve alerji bilgisi rızanızı geri alabilir veya
        hesabınızı silebilirsiniz.
      </p>
      <p>
        <strong>Yazılı başvuru:</strong> Diğer talepleriniz için kimliğinizi doğrulayan
        bilgilerle birlikte başvurunuzu yukarıdaki adrese elden veya noter aracılığıyla, kayıtlı
        elektronik posta (KEP) adresimize ({LEGAL.kepAddress}) ya da daha önce bize bildirdiğiniz
        ve sistemimizde kayıtlı e-posta adresinizden{' '}
        <a href={`mailto:${LEGAL.email}`}>{LEGAL.email}</a> adresine iletebilirsiniz. Başvurular
        en geç 30 gün içinde ücretsiz olarak sonuçlandırılır.
      </p>
      <p>
        Başvurunuzun reddedilmesi, verilen cevabı yetersiz bulmanız veya süresinde cevap
        verilmemesi halinde Kişisel Verileri Koruma Kurulu&apos;na şikâyette bulunabilirsiniz.
      </p>
    </LegalDocument>
  );
}
