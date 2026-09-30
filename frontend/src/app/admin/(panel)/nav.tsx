'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';

import { apiSend } from '@/lib/api-client';

export function AdminNavLink({
  href,
  icon,
  children,
}: {
  href: string;
  icon: string;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const active = href === '/admin' ? pathname === '/admin' : pathname.startsWith(href);

  return (
    <Link
      href={href}
      aria-current={active ? 'page' : undefined}
      className={`flex shrink-0 touch-target items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium ${
        active ? 'bg-plum-600 text-white' : 'text-ink-700 hover:bg-sand-100'
      }`}
    >
      <span aria-hidden>{icon}</span>
      {children}
    </Link>
  );
}

export function StaffLogout() {
  const router = useRouter();
  return (
    <button
      type="button"
      className="btn-secondary text-sm"
      onClick={async () => {
        await apiSend('/api/auth/logout', 'POST', { scope: 'staff' }).catch(() => undefined);
        router.push('/admin/giris');
        router.refresh();
      }}
    >
      Çıkış
    </button>
  );
}
