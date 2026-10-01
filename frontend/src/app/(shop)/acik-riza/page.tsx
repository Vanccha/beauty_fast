import type { Metadata } from 'next';
import Link from 'next/link';

import { LegalDocument } from '@/components/legal/LegalDocument';
import { LEGAL } from '@/lib/legal';
import { serverApi, type SalonInfo } from '@/lib/server-api';

export const metadata: Metadata = { title: 'Açık Rıza ve Onay Metinleri' };

/**
 * İki AYRI rıza metni. KVKK'ya göre rıza "belirli bir konuya ilişkin"
 * olmalı ve hizmet şartına bağlanamaz; bu yüzden ikisi ayrı onaylanır
 * ve ikisi de randevu almak için gerekli DEĞİLDİR.
 *
 *   #ticari-ileti — giriş formundaki isteğe bağlı kutu (müşteri verir)
 *   #saglik       — alerji kaydı; salonda personel kaydederken alınır
 */
export default async function ConsentPage() {
  const { salon } = await serverApi<{ salon: SalonInfo }>('/api/showcase');

  return (
    <LegalDocument title="Açık Rıza ve Onay Metinleri">
      <p>
        Aşağıdaki iki onay birbirinden bağımsızdır ve <strong>isteğe bağlıdır</strong>. Onay
        vermemeniz randevu almanızı veya hizmetlerimizden yararlanmanızı engellemez. Verdiğiniz
        onayı dilediğiniz zaman, gerekçe göstermeden{' '}
        <Link href="/hesabim#gizlilik">Hesabım → Gizlilik ve verilerim</Link> bölümünden geri
        alabilirsiniz. Verilerinizin nasıl işlendiğine ilişkin ayrıntılar{' '}
        <Link href="/kvkk">KVKK Aydınlatma Metni</Link>&apos;nde yer alır.
      </p>

      <h2 id="ticari-ileti">1. Ticari elektronik ileti onayı</h2>
      <p>
        {LEGAL.controllerTitle} ({salon.salonName}) tarafından; aldığım hizmetlere göre bakım
        zamanımın geldiğini hatırlatan mesajların, kampanya ve indirim duyurularının cep telefonu
        numarama <strong>WhatsApp</strong> üzerinden gönderilmesine, bu amaçla ad, telefon ve
        hizmet geçmişi bilgilerimin işlenmesine 6563 sayılı Elektronik Ticaretin Düzenlenmesi
        Hakkında Kanun ve 6698 sayılı KVKK uyarınca onay veriyorum.
      </p>
      <ul>
        <li>
          Randevu onayı ve randevudan önceki hatırlatma bu onaydan bağımsızdır; randevunuzla
          ilgili bilgilendirme olduğu için onay vermeseniz de gönderilir.
        </li>
        <li>
          Onayınızı Hesabım sayfasından geri alabilirsiniz. Geri aldığınız anda bekleyen
          hatırlatmalar iptal edilir.
        </li>
      </ul>

      <h2 id="saglik">2. Sağlık verisi (alerji bilgisi) açık rıza metni</h2>
      <p>
        Alerji ve hassasiyet bilgileri KVKK madde 6 uyarınca <strong>özel nitelikli kişisel
        veridir</strong> ve ancak açık rızanızla işlenebilir.
      </p>
      <p>
        {LEGAL.controllerTitle} ({salon.salonName}) tarafından; uygulanacak işlemlerde sağlığımın
        korunması amacıyla, salon personeline bildirdiğim alerji ve hassasiyet bilgilerimin
        müşteri kartıma kaydedilmesine, işlem öncesinde ilgili ustaya uyarı olarak
        gösterilmesine ve bu amaçla saklanmasına açık rıza veriyorum.
      </p>
      <ul>
        <li>Bu bilgi yalnızca salon personeline görünür; hiçbir üçüncü kişiyle paylaşılmaz.</li>
        <li>
          Onayınız salonda, bilgi kaydedilmeden önce personelimiz tarafından alınır ve tarihiyle
          kaydedilir.
        </li>
        <li>
          Rızanızı geri aldığınızda kayıtlı tüm alerji bilgileriniz <strong>kalıcı olarak
          silinir</strong>. Bu durumda ustanız işlem öncesi uyarı göremeyeceği için alerjinizi
          her ziyarette sözlü olarak bildirmenizi öneririz.
        </li>
      </ul>
    </LegalDocument>
  );
}
