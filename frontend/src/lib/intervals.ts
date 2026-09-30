/**
 * Aralık cebiri — zamanlama motorunun matematiksel tabanı.
 *
 * Tüm aralıklar YARIA AÇIK'tır: [start, end). Yani 10:00–10:30 ile
 * 10:30–11:00 çakışmaz. Birimler "gün içi dakika"dır (09:30 -> 570).
 *
 * Bu dosya tamamen saftır (I/O yok, Prisma yok) — birim testleri kolaydır.
 */

export interface Interval {
  start: number;
  end: number;
}

export function isValid(i: Interval): boolean {
  return Number.isFinite(i.start) && Number.isFinite(i.end) && i.end > i.start;
}

export function length(i: Interval): number {
  return Math.max(0, i.end - i.start);
}

export function totalLength(list: Interval[]): number {
  return list.reduce((sum, i) => sum + length(i), 0);
}

/** [a.start,a.end) ile [b.start,b.end) kesişiyor mu? Dokunma çakışma değildir. */
export function overlaps(a: Interval, b: Interval): boolean {
  return a.start < b.end && b.start < a.end;
}

/** `inner` tamamen `outer` içinde mi? */
export function contains(outer: Interval, inner: Interval): boolean {
  return inner.start >= outer.start && inner.end <= outer.end;
}

export function shift(list: Interval[], delta: number): Interval[] {
  return list.map((i) => ({ start: i.start + delta, end: i.end + delta }));
}

/**
 * Sıralar, geçersizleri atar ve bitişik/çakışan aralıkları birleştirir.
 * Sonuç: artan sırada, ayrık aralıklar.
 */
export function normalize(list: Interval[]): Interval[] {
  const valid = list.filter(isValid).sort((a, b) => a.start - b.start || a.end - b.end);
  const out: Interval[] = [];
  for (const cur of valid) {
    const last = out[out.length - 1];
    if (last && cur.start <= last.end) {
      // Bitişik (cur.start === last.end) olanlar da birleşir: 10:00-10:30 + 10:30-11:00 = 10:00-11:00
      last.end = Math.max(last.end, cur.end);
    } else {
      out.push({ start: cur.start, end: cur.end });
    }
  }
  return out;
}

/** base \ cuts (küme farkı). Her iki taraf da normalize edilir. */
export function subtract(base: Interval[], cuts: Interval[]): Interval[] {
  const cutsN = normalize(cuts);
  let result = normalize(base);

  for (const cut of cutsN) {
    const next: Interval[] = [];
    for (const piece of result) {
      if (!overlaps(piece, cut)) {
        next.push(piece);
        continue;
      }
      if (piece.start < cut.start) next.push({ start: piece.start, end: cut.start });
      if (cut.end < piece.end) next.push({ start: cut.end, end: piece.end });
    }
    result = next;
  }
  return result;
}

/** a ∩ b */
export function intersect(a: Interval[], b: Interval[]): Interval[] {
  const an = normalize(a);
  const bn = normalize(b);
  const out: Interval[] = [];
  let i = 0;
  let j = 0;
  while (i < an.length && j < bn.length) {
    const start = Math.max(an[i].start, bn[j].start);
    const end = Math.min(an[i].end, bn[j].end);
    if (end > start) out.push({ start, end });
    if (an[i].end < bn[j].end) i++;
    else j++;
  }
  return out;
}

/**
 * `inner`, normalize edilmiş `free` listesindeki TEK bir aralığın içinde
 * tamamen yer alıyor mu? (İki ayrı boşluğa bölünerek sığması kabul edilmez —
 * "kesintisiz blok" şartının uygulandığı yer burasıdır.)
 */
export function containedInAny(inner: Interval, free: Interval[]): boolean {
  return free.some((f) => contains(f, inner));
}

export function overlapsAny(probe: Interval, list: Interval[]): boolean {
  return list.some((i) => overlaps(probe, i));
}

/** `probe`'u içeren ilk aralığı döndürür (yoksa null). */
export function findContainer(probe: Interval, list: Interval[]): Interval | null {
  return list.find((i) => contains(i, probe)) ?? null;
}

export interface Usage {
  interval: Interval;
  quantity: number;
}

/**
 * Kapasiteli kaynaklar için "doygun" aralıkları hesaplar: eşzamanlı kullanım
 * `capacity`'ye ulaşmış (yeni iş alamayacak) zaman dilimleri.
 *
 * Süpürme (sweep-line) ile O(n log n).
 */
export function saturatedIntervals(usages: Usage[], capacity: number): Interval[] {
  if (capacity <= 0) return usages.length ? normalize(usages.map((u) => u.interval)) : [];

  type Event = { at: number; delta: number };
  const events: Event[] = [];
  for (const u of usages) {
    if (!isValid(u.interval) || u.quantity <= 0) continue;
    events.push({ at: u.interval.start, delta: u.quantity });
    events.push({ at: u.interval.end, delta: -u.quantity });
  }
  if (!events.length) return [];

  // Aynı noktada önce çıkışlar işlenir ki bitişik randevular yapay doygunluk yaratmasın.
  events.sort((a, b) => a.at - b.at || a.delta - b.delta);

  const out: Interval[] = [];
  let load = 0;
  let satStart: number | null = null;

  for (let k = 0; k < events.length; k++) {
    const at = events[k].at;
    // Aynı zaman damgasındaki tüm olayları birlikte uygula
    while (k < events.length && events[k].at === at) {
      load += events[k].delta;
      k++;
    }
    k--;

    if (load >= capacity && satStart === null) {
      satStart = at;
    } else if (load < capacity && satStart !== null) {
      out.push({ start: satStart, end: at });
      satStart = null;
    }
  }

  return normalize(out);
}
