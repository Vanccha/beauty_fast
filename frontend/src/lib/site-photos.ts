import { existsSync } from 'node:fs';
import path from 'node:path';

/**
 * ====================================================================
 * VİTRİN FOTOĞRAFLARI
 * ====================================================================
 *
 * Açılış sayfasının dekoratif fotoğrafları (kahraman görseli, mekân
 * kareleri, detay çekimleri) veritabanında tutulmaz — bunlar salonun
 * "pazarlama malzemesi"dir, işletme verisi değil. Bu yüzden doğrudan
 * `public/photos/` klasöründen okunur.
 *
 * Fotoğraflar depoda versiyonlanmaz; `npm run photos` ile indirilir
 * (bkz. `scripts/fetch-photos.mjs`). İndirilmemişse sayfa ÇÖKMEZ:
 * burası çizilmiş `hero.svg` illüstrasyonuna düşer.
 *
 * Salon kendi fotoğrafını koymak isterse aynı adla dosyayı
 * `public/photos/` içine bırakması yeterlidir; kod değişmez.
 *
 * `existsSync` istek başına çalışır ama açılış sayfası zaten
 * `force-dynamic`; ayrıca sonuç süreç ömrü boyunca önbelleklenmez
 * çünkü fotoğrafı klasöre atar atmaz görmek isteriz.
 */

const PHOTO_DIR = path.join(process.cwd(), 'public', 'photos');

/** Hiçbir fotoğraf yoksa kullanılan çizilmiş illüstrasyon. */
const FALLBACK = '/hero.svg';

/**
 * `public/photos/<name>` varsa yolunu, yoksa `null` döndürür.
 *
 * @param name Dosya adı — uzantısıyla birlikte (`hero.jpg`)
 */
export function photo(name: string): string | null {
  return existsSync(path.join(PHOTO_DIR, name)) ? `/photos/${name}` : null;
}

/**
 * Sırayla dener, ilk bulunanı döndürür; hiçbiri yoksa illüstrasyona düşer.
 * Bir bölüm görselsiz kalmasın diye kullanılır.
 */
export function photoOrFallback(...names: string[]): string {
  for (const name of names) {
    const found = photo(name);
    if (found) return found;
  }
  return FALLBACK;
}

/** Verilen adlardan yalnızca gerçekten var olanları döndürür. */
export function photoSet(...names: string[]): string[] {
  return names.map(photo).filter((p): p is string => p !== null);
}

/** Vitrin fotoğrafları hiç indirilmemiş mi? (kurulum uyarısı için) */
export function hasPhotos(): boolean {
  return photo('hero.jpg') !== null;
}
