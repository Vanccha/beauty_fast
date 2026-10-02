import { Info } from 'lucide-react';
import Link from 'next/link';

import { LEGAL } from '@/lib/legal';

/**
 * Hukuki metin sayfalarının ortak kabuğu: başlık, güncelleme tarihi,
 * temsili-metin uyarısı ve diğer metinlere bağlantılar.
 */
export function LegalDocument({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="page-shell max-w-3xl pb-8 pt-10 md:pt-14">
      {LEGAL.isRepresentative && (
        <div className="alert alert-warning mb-8 max-w-prose">
          <Info size={18} strokeWidth={1.5} aria-hidden className="mt-0.5 shrink-0" />
          <p>
            <strong>Temsili metindir.</strong> Şirket unvanı, MERSİS/vergi ve başvuru adresleri
            örnektir; salonun kendi bilgileriyle güncellenecek ve hukuki incelemeden geçirilecektir.
          </p>
        </div>
      )}

      <article className="legal">
        <div className="eyebrow">Hukuki metin</div>
        <h1 className="display mt-3 text-3xl md:text-4xl">{title}</h1>
        <div className="muted mt-3 tabular-nums">Son güncelleme: {LEGAL.lastUpdated}</div>
        {children}
      </article>

      <nav aria-label="Diğer metinler" className="mt-14 flex flex-wrap gap-3 border-t border-sand-200 pt-6">
        <Link href="/kvkk" className="btn-secondary btn-sm">
          Aydınlatma Metni
        </Link>
        <Link href="/acik-riza" className="btn-secondary btn-sm">
          Açık Rıza Metinleri
        </Link>
        <Link href="/cerez-politikasi" className="btn-secondary btn-sm">
          Çerez Politikası
        </Link>
      </nav>
    </div>
  );
}

/** Veri sorumlusu kimlik bloğu — her metinde aynı. */
export function ControllerCard({
  salonName,
  address,
  phone,
}: {
  salonName: string;
  address: string | null;
  phone: string | null;
}) {
  return (
    <dl className="card mt-4 grid gap-x-4 gap-y-1.5 p-5 text-sm md:p-6 sm:grid-cols-[10rem_1fr]">
      <dt className="muted">Veri sorumlusu</dt>
      <dd className="font-medium">{LEGAL.controllerTitle}</dd>
      <dt className="muted">İşletme adı</dt>
      <dd>{salonName}</dd>
      {address && (
        <>
          <dt className="muted">Adres</dt>
          <dd>{address}</dd>
        </>
      )}
      <dt className="muted">MERSİS No</dt>
      <dd>{LEGAL.mersisNo}</dd>
      <dt className="muted">Vergi bilgisi</dt>
      <dd>{LEGAL.taxInfo}</dd>
      <dt className="muted">E-posta</dt>
      <dd>
        <a href={`mailto:${LEGAL.email}`} className="text-plum-700 underline">
          {LEGAL.email}
        </a>
      </dd>
      <dt className="muted">KEP</dt>
      <dd>{LEGAL.kepAddress}</dd>
      {phone && (
        <>
          <dt className="muted">Telefon</dt>
          <dd>0{phone}</dd>
        </>
      )}
    </dl>
  );
}
