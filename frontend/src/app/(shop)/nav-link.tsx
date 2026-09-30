'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

/**
 * Aktif sayfayı işaretleyen bağlantı. `usePathname` istemci hook'u
 * olduğu için ayrı bir client bileşende tutulur — layout sunucu bileşeni
 * kalır ve oturum bilgisini sunucuda okumaya devam eder.
 */
export function NavLink({
  href,
  children,
  icon,
  variant = 'top',
}: {
  href: string;
  children: React.ReactNode;
  icon?: string;
  variant?: 'top' | 'bottom';
}) {
  const pathname = usePathname();
  const active = href === '/' ? pathname === '/' : pathname.startsWith(href);

  if (variant === 'bottom') {
    return (
      <Link
        href={href}
        aria-current={active ? 'page' : undefined}
        className={`flex flex-1 touch-target flex-col items-center justify-center gap-0.5 py-2 text-xs font-medium ${
          active ? 'text-plum-700' : 'text-ink-500'
        }`}
      >
        <span aria-hidden className="text-lg leading-none">
          {icon}
        </span>
        {children}
      </Link>
    );
  }

  return (
    <Link
      href={href}
      aria-current={active ? 'page' : undefined}
      className={`btn-ghost ${active ? 'bg-sand-100 text-plum-700' : ''}`}
    >
      {children}
    </Link>
  );
}
