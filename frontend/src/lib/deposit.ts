/** Kapora (deposit) ortak tipleri ve biçimleyicileri — admin + müşteri ekranları. */

/** Takvim / detay için kapora özeti (backend `deposit.admin_view`). */
export interface DepositSummary {
  /** NONE | AWAITING | PAID | REFUND_DUE | REFUNDED | FORFEITED */
  status: string;
  amount: number | null;
  requestedAt: string | null;
  paidAt: string | null;
  refundDueAt: string | null;
  refundedAt: string | null;
  /** Kapora talebinden bu yana gecikme süresi (ayarlı dakika) aşıldı mı? */
  overdue: boolean;
}

/** "Kapora bekleyenler" / "İade bekleyenler" listesindeki satır. */
export interface DepositRow {
  id: number;
  version: number;
  date: string;
  dateLabel: string;
  startLabel: string;
  customer: { id: number; name: string; phone: string };
  payer: { id: number; name: string; phone: string } | null;
  services: string[];
  totalPrice: number;
  amount: number | null;
  status: string;
  depositStatus: string;
  groupId: string | null;
  requestedAt: string | null;
  refundDueAt: string | null;
  /** Bekleyen kapora için */
  ageMinutes?: number;
  deadlineMinutes?: number;
  reference?: string;
  groupSize?: number;
  groupAmount?: number;
  /** İade için: kalan dakika (negatifse gecikti) */
  remainingMinutes?: number;
  overdue: boolean;
}

export interface DepositLists {
  enabled: boolean;
  deadlineMinutes: number;
  awaiting: DepositRow[];
  refunds: DepositRow[];
}

/** "35 dk", "2 sa 10 dk", "1 gün 3 sa" */
export function spanLabel(totalMinutes: number): string {
  const m = Math.max(0, Math.round(totalMinutes));
  if (m < 60) return `${m} dk`;
  if (m < 24 * 60) {
    const h = Math.floor(m / 60);
    const rest = m % 60;
    return rest ? `${h} sa ${rest} dk` : `${h} sa`;
  }
  const d = Math.floor(m / (24 * 60));
  const h = Math.floor((m % (24 * 60)) / 60);
  return h ? `${d} gün ${h} sa` : `${d} gün`;
}

/** İade süresi: "31 sa kaldı" / "5 sa gecikti". */
export function refundRemainingLabel(remainingMinutes: number): string {
  return remainingMinutes >= 0
    ? `${spanLabel(remainingMinutes)} kaldı`
    : `${spanLabel(-remainingMinutes)} gecikti`;
}
