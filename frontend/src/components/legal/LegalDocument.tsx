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
    <div className="page-shell max-w-3xl pt-6">
      {LEGAL.isRepresentative && (
        <p className="mb-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <strong>Temsili metindir.</strong> Şirket unvanı, MERSİS/vergi ve başvuru adresleri
          örnektir; salonun kendi bilgileriyle güncellenecek ve hukuki incelemeden geçirilecektir.
        </p>
      )}

      <article className="legal">
        <h1 className="display text-2xl md:text-3xl">{title}</h1>
        <p className="muted mt-1">Son güncelleme: {LEGAL.lastUpdated}</p>
        {children}
      </article>

      <nav aria-label="Diğer metinler" className="mt-10 flex flex-wrap gap-2 border-t border-sand-200 pt-5">
        <Link href="/kvkk" className="btn-secondary text-sm">
          Aydınlatma Metni
        </Link>
        <Link href="/acik-riza" className="btn-secondary text-sm">
          Açık Rıza Metinleri
        </Link>
        <Link href="/cerez-politikasi" className="btn-secondary text-sm">
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
    <dl className="card mt-4 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-[10rem_1fr]">
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
