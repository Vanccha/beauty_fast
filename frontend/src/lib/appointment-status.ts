/** Randevu durumları için Türkçe etiket ve rozet tonu (admin + müşteri ekranları). */
export const APPOINTMENT_STATUS_LABELS: Record<string, string> = {
  PENDING: 'Bekliyor',
  CONFIRMED: 'Onaylandı',
  COMPLETED: 'Tamamlandı',
  CANCELLED: 'İptal edildi',
  NO_SHOW: 'Gelmedi',
};

export function appointmentStatusLabel(status: string): string {
  return APPOINTMENT_STATUS_LABELS[status] ?? status;
}

/** Rozet sınıfları (tema belirteçleri). */
export function appointmentStatusTone(status: string): string {
  switch (status) {
    case 'COMPLETED':
      return 'bg-success-50 text-success-700';
    case 'NO_SHOW':
      return 'bg-danger-50 text-danger-700';
    case 'CANCELLED':
      return 'bg-sand-100 text-ink-500';
    case 'CONFIRMED':
      return 'bg-plum-50 text-plum-700';
    default:
      return 'bg-sand-100 text-ink-700';
  }
}

/** Küçük durum noktası rengi. */
export function appointmentStatusDot(status: string): string {
  switch (status) {
    case 'COMPLETED':
      return 'bg-success-600';
    case 'NO_SHOW':
      return 'bg-danger-600';
    case 'CONFIRMED':
      return 'bg-plum-600';
    default:
      return 'bg-sand-300';
  }
}

/**
 * KAPORA. `deposit_status`: NONE | AWAITING | PAID | REFUND_DUE | REFUNDED | FORFEITED.
 * Kapora beklerken randevu PENDING'dir; bu durum ekranda "Kapora bekleniyor" görünür.
 */
export type DepositStatus = 'NONE' | 'AWAITING' | 'PAID' | 'REFUND_DUE' | 'REFUNDED' | 'FORFEITED';

export function isAwaitingDeposit(status: string, depositStatus?: string | null): boolean {
  return status === 'PENDING' && depositStatus === 'AWAITING';
}

/** Durum + kapora → etiket (PENDING + AWAITING = "Kapora bekleniyor"). */
export function appointmentLabel(status: string, depositStatus?: string | null): string {
  return isAwaitingDeposit(status, depositStatus) ? 'Kapora bekleniyor' : appointmentStatusLabel(status);
}

export function appointmentTone(status: string, depositStatus?: string | null): string {
  return isAwaitingDeposit(status, depositStatus)
    ? 'bg-brass-300/30 text-brass-700'
    : appointmentStatusTone(status);
}

export function appointmentDot(status: string, depositStatus?: string | null): string {
  return isAwaitingDeposit(status, depositStatus) ? 'bg-brass-500' : appointmentStatusDot(status);
}

/** Küçük kapora rozeti (Ödendi / İade bekliyor / İade edildi / Yandı); yoksa null. */
export function depositBadge(depositStatus?: string | null): { label: string; tone: string } | null {
  switch (depositStatus) {
    case 'PAID':
      return { label: 'Kapora ödendi', tone: 'bg-success-50 text-success-700' };
    case 'REFUND_DUE':
      return { label: 'İade bekliyor', tone: 'bg-brass-300/30 text-brass-700' };
    case 'REFUNDED':
      return { label: 'İade edildi', tone: 'bg-sand-100 text-ink-500' };
    case 'FORFEITED':
      return { label: 'Kapora yandı', tone: 'bg-danger-50 text-danger-700' };
    default:
      return null;
  }
}

/** Kapora politikası (müşteriye gösterilen metin; backend `deposit.POLICY_TEXT` ile aynı). */
export const DEPOSIT_POLICY =
  'Randevuya 1 saatten az kala iptal yapılamaz; bu durumda kapora iade edilmez. ' +
  'Daha önce yapılan iptallerde kapora 48 saat içinde tarafınıza gönderilir.';
