import { House, Images, MessageSquareQuote, Users } from 'lucide-react';
import Link from 'next/link';

import { serverApi, type MeResponse, type SalonInfo } from '@/lib/server-api';
import { NavLink } from './nav-link';
import { SiteHeader } from './site-header';

/**
 * Müşteri arayüzü kabuğu.
 *
 * Mobile-first: gezinme altta sabit bir çubukta (başparmak erişimi),
 * `md:` üstünde üst bara taşınır. Tüm bağlantılar 44 px dokunma hedefi.
 *
 * DİKKAT — `main` artık kenar boşluğu UYGULAMAZ. Açılış sayfası tam
 * genişlikte fotoğraf serebilsin diye boşluk sorumluluğu sayfalara
 * devredildi; sıradan sayfalar içeriğini `.page-shell` ile sarar.
 */
export default async function ShopLayout({ children }: { children: React.ReactNode }) {
  // Salon bilgisi ve oturum FastAPI'den gelir; kabuk veritabanını bilmez.
  const [showcase, me] = await Promise.all([
    serverApi<{ salon: SalonInfo }>('/api/showcase'),
    serverApi<MeResponse>('/api/me'),
  ]);

  const customer = me.customer;
  const branch = {
    name: showcase.salon.branchName,
    address: showcase.salon.address,
    salon: { name: showcase.salon.salonName, phone: showcase.salon.phone },
  };

  const links = [
    { href: '/', label: 'Ana Sayfa', icon: <House size={20} strokeWidth={1.5} /> },
    // Portfolyo, yorumlar ve ekip ana sayfadaki bölümlerdir (tek sayfa düzeni).
    { href: '/#portfolyo', label: 'Portfolyo', icon: <Images size={20} strokeWidth={1.5} /> },
    { href: '/#yorumlar', label: 'Yorumlar', icon: <MessageSquareQuote size={20} strokeWidth={1.5} /> },
    { href: '/#ekip', label: 'Ekibimiz', icon: <Users size={20} strokeWidth={1.5} /> },
  ];

  return (
    <div className="flex min-h-dvh w-full flex-col">
      <SiteHeader
        salonName={branch.salon.name}
        customerName={customer?.firstName ?? null}
        links={links.map(({ href, label }) => ({ href, label }))}
      />

      <main className="flex-1">{children}</main>

      {/* ================= ALT BİLGİ ================= */}
      <footer className="mt-20 bg-ink-900 pb-[calc(4.5rem+env(safe-area-inset-bottom))] text-sand-200/80 lg:pb-0">
        <div className="bleed grid gap-10 py-14 sm:grid-cols-2 md:grid-cols-3">
          <div>
            <p className="display text-2xl text-sand-50">{branch.salon.name}</p>
            <p className="mt-3 max-w-xs text-sm text-sand-200/70">{branch.address}</p>
            {branch.salon.phone && (
              <a
                href={`tel:0${branch.salon.phone}`}
                className="mt-4 inline-flex text-sm font-medium text-sand-50 hover:text-brass-300"
              >
                0{branch.salon.phone}
              </a>
            )}
          </div>

          <nav aria-label="Alt gezinme">
            <p className="eyebrow !text-brass-300">Sayfalar</p>
            <ul className="mt-4 space-y-2.5">
              {links.map((l) => (
                <li key={l.href}>
                  <Link href={l.href} className="text-sm text-sand-200/80 transition-colors hover:text-sand-50">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          <div>
            <p className="eyebrow !text-brass-300">Randevu</p>
            <p className="mt-4 text-sm text-sand-200/70">
              Uygun saatleri üye olmadan görebilirsin. Randevu için tek adımlık telefon
              doğrulaması yeterli.
            </p>
            <Link href="/randevu" className="btn-light btn-sm mt-5 inline-flex">
              Randevu al
            </Link>
          </div>
        </div>

        <div className="border-t border-white/10 py-5">
          <div className="bleed flex flex-col gap-2 text-xs text-sand-200/60 sm:flex-row sm:items-center sm:justify-between">
            <p>
              © {new Date().getFullYear()} {branch.salon.name} · {branch.name}
            </p>
            <nav aria-label="Yasal metinler" className="flex flex-wrap gap-x-4 gap-y-1">
              <Link href="/kvkk" className="transition-colors hover:text-sand-50">
                KVKK Aydınlatma Metni
              </Link>
              <Link href="/acik-riza" className="transition-colors hover:text-sand-50">
                Açık Rıza Metinleri
              </Link>
              <Link href="/cerez-politikasi" className="transition-colors hover:text-sand-50">
                Çerez Politikası
              </Link>
            </nav>
          </div>
        </div>
      </footer>

      {/* Mobil alt gezinme — başparmakla erişilebilir bölge */}
      {/* Ana ekran çubuğu (iPhone) altında kalmasın diye güvenli alan kadar iç boşluk. */}
      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-sand-200 bg-sand-50/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden">
        <div className="mx-auto flex max-w-5xl">
          {links.map((l) => (
            <NavLink key={l.href} href={l.href} variant="bottom" icon={l.icon}>
              {l.label}
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
