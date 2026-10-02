import { redirect } from 'next/navigation';

/** Yorumlar artık açılış sayfasının bir bölümü → `/#yorumlar`. */
export default function ReviewsRedirect() {
  redirect('/#yorumlar');
}
