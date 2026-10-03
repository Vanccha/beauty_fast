'use client';

import { usePathname } from 'next/navigation';

/** Salon numarası → wa.me numarası (yalnızca rakam, ülke kodlu). */
function waNumber(phone: string): string | null {
  const digits = phone.replace(/\D/g, '');
  if (!digits) return null;
  if (phone.trim().startsWith('+')) return digits;
  const local = digits.replace(/^0+/, '');
  return local.length === 10 ? `90${local}` : local.startsWith('90') ? local : null;
}

/**
 * Sağ altta yüzen WhatsApp düğmesi. Randevu akışında (`/randevu*`) gizlidir:
 * oradaki sabit alt eylem çubuğunu örtmesin. Mobilde alttaki sabit menünün
 * üstünde durur; z-index modalların altındadır.
 */
export function WhatsAppFab({ phone }: { phone: string | null }) {
  const pathname = usePathname();
  if (!phone || pathname.startsWith('/randevu') && !pathname.startsWith('/randevularim')) return null;

  const number = waNumber(phone);
  if (!number) return null;

  const href = `https://wa.me/${number}?text=${encodeURIComponent(
    'Merhaba, randevu hakkında bilgi almak istiyorum.',
  )}`;

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener"
      aria-label="WhatsApp'tan yazın"
      className="fixed right-4 z-20 flex h-12 items-center justify-center gap-2 rounded-full bg-plum-600 text-white shadow-lg shadow-ink-900/25 transition-colors hover:bg-plum-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-plum-600 bottom-[calc(4.5rem+env(safe-area-inset-bottom))] w-12 lg:bottom-6 lg:right-6 lg:w-auto lg:px-5"
    >
      <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden="true">
        <path d="M17.47 14.38c-.3-.15-1.76-.87-2.03-.97-.27-.1-.47-.15-.67.15-.2.3-.77.97-.94 1.17-.17.2-.35.22-.65.07-.3-.15-1.26-.46-2.4-1.48-.89-.79-1.49-1.77-1.66-2.07-.17-.3-.02-.46.13-.61.14-.13.3-.35.45-.52.15-.17.2-.3.3-.5.1-.2.05-.37-.02-.52-.08-.15-.67-1.62-.92-2.22-.24-.58-.49-.5-.67-.51h-.57c-.2 0-.52.07-.8.37-.27.3-1.04 1.02-1.04 2.48s1.07 2.88 1.22 3.08c.15.2 2.1 3.2 5.08 4.49.71.31 1.26.49 1.7.63.71.23 1.36.2 1.87.12.57-.08 1.76-.72 2.01-1.41.25-.69.25-1.29.17-1.41-.07-.12-.27-.2-.57-.35zM12.05 21.8h-.01a9.87 9.87 0 0 1-5.03-1.38l-.36-.21-3.74.98 1-3.65-.24-.37a9.86 9.86 0 0 1-1.51-5.26c0-5.45 4.44-9.88 9.89-9.88a9.82 9.82 0 0 1 6.99 2.9 9.82 9.82 0 0 1 2.89 6.99c0 5.45-4.44 9.88-9.88 9.88zM20.52 3.45A11.8 11.8 0 0 0 12.05 0C5.5 0 .16 5.34.16 11.89c0 2.1.55 4.14 1.59 5.95L.06 24l6.3-1.65a11.88 11.88 0 0 0 5.68 1.45h.01c6.55 0 11.89-5.34 11.89-11.89 0-3.18-1.24-6.17-3.48-8.41z" />
      </svg>
      <span className="hidden text-sm font-medium lg:inline">WhatsApp&apos;tan yaz</span>
    </a>
  );
}
