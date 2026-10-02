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
    { href: '/', label: 'Ana Sayfa', icon: '🏠' },
    { href: '/randevu', label: 'Randevu', icon: '📅' },
    { href: '/portfolyo', label: 'Portfolyo', icon: '✨' },
    { href: '/hesabim', label: 'Hesabım', icon: '👤' },
  ];

  // Üst barda gösterilen ama alt çubuğa sığmayan ek sayfalar.
  const secondaryLinks = [{ href: '/yorumlar', label: 'Yorumlar' }];

  return (
    <div className="flex min-h-dvh w-full flex-col">
      <SiteHeader
        salonName={branch.salon.name}
        customerName={customer?.firstName ?? null}
        links={[...links, ...secondaryLinks]}
      />

      <main className="flex-1 pb-[calc(7rem+env(safe-area-inset-bottom))] md:pb-12">{children}</main>

      {/* ================= ALT BİLGİ ================= */}
      <footer className="mt-12 border-t border-sand-200 bg-white">
        <div className="bleed grid gap-8 py-10 sm:grid-cols-2 md:grid-cols-3">
          <div>
            <p className="display text-lg">{branch.salon.name}</p>
            <p className="muted mt-2 max-w-xs">{branch.address}</p>
            {branch.salon.phone && (
              <a
                href={`tel:0${branch.salon.phone}`}
                className="mt-3 inline-flex text-sm font-medium text-plum-700"
              >
                0{branch.salon.phone}
              </a>
            )}
          </div>

          <nav aria-label="Alt gezinme">
            <p className="text-sm font-semibold">Sayfalar</p>
            <ul className="mt-3 space-y-2">
              {[...links, ...secondaryLinks].map((l) => (
                <li key={l.href}>
                  <Link href={l.href} className="text-sm text-ink-500 hover:text-plum-700">
                    {l.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          <div>
            <p className="text-sm font-semibold">Randevu</p>
            <p className="muted mt-3">
              Uygun saatleri üye olmadan görebilirsin. Randevu için tek adımlık telefon
              doğrulaması yeterli.
            </p>
            <Link href="/randevu" className="btn-primary mt-4 inline-flex">
              Randevu al
            </Link>
          </div>
        </div>

        <div className="border-t border-sand-100 py-4">
          <div className="bleed flex flex-col gap-2 text-xs text-ink-500 sm:flex-row sm:items-center sm:justify-between">
            <p>
              © {new Date().getFullYear()} {branch.salon.name} · {branch.name}
            </p>
            <nav aria-label="Yasal metinler" className="flex flex-wrap gap-x-4 gap-y-1">
              <Link href="/kvkk" className="hover:text-plum-700">
                KVKK Aydınlatma Metni
              </Link>
              <Link href="/acik-riza" className="hover:text-plum-700">
                Açık Rıza Metinleri
              </Link>
              <Link href="/cerez-politikasi" className="hover:text-plum-700">
                Çerez Politikası
              </Link>
            </nav>
          </div>
        </div>
      </footer>

      {/* Mobil alt gezinme — başparmakla erişilebilir bölge */}
      {/* Ana ekran çubuğu (iPhone) altında kalmasın diye güvenli alan kadar iç boşluk. */}
      <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-sand-200 bg-white/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
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
