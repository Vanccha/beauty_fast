import { redirect } from 'next/navigation';

/** Eski "Hesabım" bağlantıları ve PWA kısayolu → Randevu Sorgula. */
export default function AccountRedirect() {
  redirect('/randevularim');
}
