'use client';

import { useRouter } from 'next/navigation';

import { PhoneVerify } from '@/components/auth/PhoneVerify';

/** Oturum yokken Randevu Sorgula girişi; doğrulama sonrası `next`'e ya da sayfa yenilemeye gider. */
export function VerifyGate({ next }: { next: string | null }) {
  const router = useRouter();
  return (
    <div className="px-5 py-12 md:py-20">
      <PhoneVerify
        title="Randevu Sorgula"
        description="Numarana gelen kodla randevularını görüntüle"
        onVerified={() => {
          if (next) router.push(next);
          router.refresh();
        }}
      />
    </div>
  );
}
