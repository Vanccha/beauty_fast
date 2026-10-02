/**
 * ====================================================================
 * ENGAGEMENT ROZETLERİ — ETİK SINIR
 * ====================================================================
 *
 * Bu bileşenlerin gösterdiği HER SAYI gerçek bir veritabanı kaydından
 * gelir:
 *
 *   - "3 kişi bu saate baktı"  → `SlotViewEvent` tekil `viewerKey` sayımı
 *   - "son 2 slot"             → zamanlama motorunun ürettiği gerçek slot sayısı
 *
 * UYDURMA SAYAÇ, sahte geri sayım veya "az kaldı" baskısı YOKTUR.
 * Ayrıca `Customer.engagementOptIn === false` ise hiçbiri gösterilmez —
 * `optIn` bayrağı bu dosyadaki her bileşene props olarak geçer ve
 * `false` iken bileşen `null` döner.
 */

import { Eye, Hourglass } from 'lucide-react';

export function ViewCountBadge({
  count,
  optIn,
}: {
  count: number;
  optIn: boolean;
}) {
  // 2'nin altındaki sayılar bilgi taşımaz, gürültü yapar.
  if (!optIn || count < 2) return null;

  return (
    <span className="badge bg-warning-50 text-warning-600" title="Gerçek görüntülenme sayısı">
      <Eye size={14} strokeWidth={1.5} aria-hidden />
      {count} kişi baktı
    </span>
  );
}

export function ScarcityBadge({
  remainingSlots,
  optIn,
}: {
  remainingSlots: number;
  optIn: boolean;
}) {
  if (!optIn || remainingSlots === 0 || remainingSlots > 3) return null;

  return (
    <span className="badge bg-danger-50 text-danger-700">
      Bugün {remainingSlots} uygun saat kaldı
    </span>
  );
}

export function OpportunityBadge({
  discountRate,
  label,
}: {
  discountRate: number;
  label: string;
}) {
  if (discountRate <= 0) return null;

  return (
    <span className="badge bg-success-50 text-success-700">
      %{Math.round(discountRate * 100)} {label}
    </span>
  );
}

/**
 * "Gölge" rozeti: bu slot, başka bir randevunun bekleme süresine
 * yerleşiyor. Müşteriye neden bu saatin açıldığı dürüstçe anlatılır.
 */
export function ShadowBadge() {
  return (
    <span
      className="badge bg-brass-300/20 text-brass-700"
      title="Bu saat, ustanın başka bir işlemde beklediği süreye denk geliyor"
    >
      <Hourglass size={14} strokeWidth={1.5} aria-hidden />
      Ara saat
    </span>
  );
}
