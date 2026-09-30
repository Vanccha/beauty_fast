import { existsSync } from 'node:fs';
import path from 'node:path';

/**
 * ====================================================================
 * AÇILIŞ GÖRSELİ ÇÖZÜMLEME
 * ====================================================================
 *
 * Depoda telifli bir fotoğraf tutulmuyor; varsayılan olarak elle çizilmiş
 * `public/hero.svg` illüstrasyonu kullanılır.
 *
 * Salon kendi fotoğrafını koymak isterse `public/` içine `hero.jpg`
 * (veya `.jpeg` / `.png` / `.webp`) bırakması yeterlidir — burası onu
 * otomatik tercih eder, kod değişikliği gerekmez.
 *
 * Dosya varlığı istek başına kontrol edilir. Sayfa zaten
 * `dynamic = 'force-dynamic'` olduğu için bu ek bir maliyet getirmez ve
 * fotoğrafı koyar koymaz sunucuyu yeniden başlatmadan görürsünüz.
 */

/**
 * Tercih sırası: salonun `public/` köküne elle koyduğu fotoğraf en
 * öncelikli (işletmenin kendi karesi her şeyin önüne geçer), sonra
 * `npm run photos` ile inen vitrin fotoğrafı, en sonda illüstrasyon.
 */
const CANDIDATES = [
  'hero.jpg',
  'hero.jpeg',
  'hero.png',
  'hero.webp',
  'photos/hero.jpg',
  'hero.svg',
] as const;

export interface HeroImage {
  url: string;
  /** Gerçek bir fotoğraf mı, yoksa yedek illüstrasyon mu? */
  isPhoto: boolean;
}

export function resolveHeroImage(): HeroImage {
  const publicDir = path.join(process.cwd(), 'public');

  for (const name of CANDIDATES) {
    if (existsSync(path.join(publicDir, name))) {
      return { url: `/${name}`, isPhoto: !name.endsWith('.svg') };
    }
  }

  // hero.svg silinmiş olsa bile sayfa çökmemeli.
  return { url: '/hero.svg', isPhoto: false };
}
