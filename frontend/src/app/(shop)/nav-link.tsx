'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { isLinkActive, useActiveSection } from './use-active-section';

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
  icon?: React.ReactNode;
  variant?: 'top' | 'bottom';
}) {
  const pathname = usePathname();
  const section = useActiveSection();
  const active = isLinkActive(href, pathname, section);

  if (variant === 'bottom') {
    return (
      <Link
        href={href}
        aria-current={active ? 'page' : undefined}
        className={`relative flex flex-1 touch-target flex-col items-center justify-center gap-1 py-2.5 text-[11px] font-semibold tracking-[0.06em] transition-colors ${
          active ? 'text-ink-900' : 'text-ink-400'
        }`}
      >
        {active && <span aria-hidden className="absolute inset-x-6 top-0 h-0.5 bg-brass-500" />}
        <span aria-hidden className="grid h-5 place-items-center leading-none">
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
      className={`btn-ghost ${active ? 'bg-plum-50 text-plum-600' : ''}`}
    >
      {children}
    </Link>
  );
}
