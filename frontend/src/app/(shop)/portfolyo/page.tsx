import { redirect } from 'next/navigation';

/** Portfolyo artık açılış sayfasının bir bölümü → `/#portfolyo`. */
export default function PortfolioRedirect() {
  redirect('/#portfolyo');
}
