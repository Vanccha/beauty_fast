// =====================================================================
// GERÇEK FOTOĞRAF İNDİRİCİ  —  `npm run photos`
// =====================================================================
//
// Açılış sayfası bir güzellik salonunu PAZARLAMAK zorunda; soyut degrade
// yer tutucular bunu yapamaz. Bu betik, salonun vitrinini kuran yüksek
// çözünürlüklü fotoğrafları `public/photos/` altına indirir.
//
// Neden depoya gömülü değil de indiriliyor?
//   - Depo ikili dosyalarla şişmesin (toplam ~15 MB).
//   - Salon kendi fotoğraflarını koyduğunda çakışma olmasın: aynı
//     dosya adını `public/photos/` içine bırakmak yeterlidir, betik
//     var olan dosyanın üzerine YAZMAZ (`--force` verilmedikçe).
//
// Kaynak: Unsplash (Unsplash License — ticari kullanım serbest, atıf
// zorunlu değil ama nezaketen `public/photos/CREDITS.md` yazılır).
//
// Kullanım:
//   node scripts/fetch-photos.mjs           # eksikleri indir
//   node scripts/fetch-photos.mjs --force   # hepsini yeniden indir
//
// Fotoğraflar indirilmezse sistem çökmez: `site-photos.ts` ve seed,
// dosya yoksa çizilmiş SVG illüstrasyonlara düşer.
// =====================================================================

import { mkdir, writeFile, access } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const ROOT = process.cwd();
const OUT_DIR = path.join(ROOT, 'public', 'photos');
const FORCE = process.argv.includes('--force');

/** Unsplash görsel CDN'i: kırpma/boyut/kalite parametreleri URL'de. */
const CDN = 'https://images.unsplash.com/photo-';

/**
 * @typedef {object} PhotoDef
 * @property {string} file      Hedef dosya adı (public/photos/ altında)
 * @property {string} id        Unsplash fotoğraf kimliği
 * @property {number} w         İndirme genişliği (px)
 * @property {number} [h]       Kırpma yüksekliği (verilirse sabit oran)
 * @property {boolean} [faces]  Yüz odaklı kırpma (personel portreleri)
 * @property {string} alt       Fotoğrafın içeriği (CREDITS.md için)
 */

/**
 * Fotoğraf listesi.
 *
 * Dosya adları ANLAMLIDIR: kod bu adlara göre arar. Bir fotoğrafı
 * değiştirmek istersen aynı adla kendi dosyanı koy, kod değişmez.
 */
const PHOTOS = /** @type {PhotoDef[]} */ ([
  // --- Kahraman & mekân -------------------------------------------------
  { file: 'hero.jpg', id: '1521590832167-7bcbfaa6381f', w: 2400, h: 1500, alt: 'Pudra rengi koltuklarıyla salon çalışma alanı' },
  { file: 'interior-1.jpg', id: '1633681926022-84c23e8cb2d6', w: 1800, h: 1200, alt: 'Aydınlık modern kuaför salonu' },
  { file: 'interior-2.jpg', id: '1600948836101-f9ffda59d250', w: 1800, h: 1200, alt: 'Yuvarlak aynalı siyah tasarım salon' },
  { file: 'interior-3.jpg', id: '1633681926035-ec1ac984418a', w: 1800, h: 1200, alt: 'Geniş açı salon iç mekân' },

  // --- Kategori kapakları (slug ile birebir eşleşir) --------------------
  { file: 'kategori-tirnak.jpg', id: '1607779097040-26e80aa78e66', w: 1200, h: 1600, alt: 'Gri ve simli tonlarda kalıcı oje' },
  { file: 'kategori-sac.jpg', id: '1554519934-e32b1629d9ee', w: 1200, h: 1600, alt: 'Balyajlı sarı saç, arkadan' },
  { file: 'kategori-kas-kirpik.jpg', id: '1487412947147-5cebf100ffc2', w: 1200, h: 1600, alt: 'Göz ve kaş makyajı uygulaması' },
  { file: 'kategori-cilt.jpg', id: '1596178065887-1198b6148b2b', w: 1200, h: 1600, alt: 'Yüz bakımı maske uygulaması' },

  // --- Portfolyo (seed'deki işlerle eşleşir) ---------------------------
  { file: 'is-balyaj.jpg', id: '1554519934-e32b1629d9ee', w: 1400, h: 1400, alt: 'Küllü kumral balyaj' },
  { file: 'is-fon.jpg', id: '1562322140-8baeececf3df', w: 1400, h: 1400, alt: 'Fön çekimi' },
  { file: 'is-uzun-sac.jpg', id: '1522337360788-8b13dee7a37e', w: 1400, h: 1400, alt: 'Sağlıklı uzun dalgalı saç' },
  { file: 'is-yikama.jpg', id: '1595476108010-b4d1f102b1b1', w: 1400, h: 1400, alt: 'Yıkama ünitesinde saç bakımı' },
  { file: 'is-fantezi-renk.jpg', id: '1470259078422-826894b933aa', w: 1400, h: 1400, alt: 'Gül kurusu fantezi saç rengi' },
  { file: 'is-nude-oje.jpg', id: '1607779097040-26e80aa78e66', w: 1400, h: 1400, alt: 'Nude kalıcı oje' },
  { file: 'is-nail-art-kirmizi.jpg', id: '1519014816548-bf5fe059798b', w: 1400, h: 1400, alt: 'Kırmızı el yazısı nail art' },
  { file: 'is-nail-art-kahve.jpg', id: '1604654894610-df63bc536371', w: 1400, h: 1400, alt: 'Kahve tonlarında nail art' },
  { file: 'is-fusya-oje.jpg', id: '1522337660859-02fbefca4702', w: 1400, h: 1400, alt: 'Fuşya oje uygulaması' },
  { file: 'is-makyaj.jpg', id: '1487412947147-5cebf100ffc2', w: 1400, h: 1400, alt: 'Kaş ve göz makyajı' },
  { file: 'is-hydrafacial.jpg', id: '1552693673-1bf958298935', w: 1400, h: 1400, alt: 'Hydrafacial uygulaması' },
  { file: 'is-derin-temizlik.jpg', id: '1616394584738-fc6e612e71b9', w: 1400, h: 1400, alt: 'Derin temizlik maskesi' },

  // --- Ekip portreleri (yüz odaklı kare kırpma) ------------------------
  { file: 'ekip-1.jpg', id: '1580489944761-15a19d654956', w: 900, h: 900, faces: true, alt: 'Kuaför portresi' },
  { file: 'ekip-2.jpg', id: '1573496359142-b8d87734a5a2', w: 900, h: 900, faces: true, alt: 'Salon yöneticisi portresi' },
  { file: 'ekip-3.jpg', id: '1494790108377-be9c29b29330', w: 900, h: 900, faces: true, alt: 'Tırnak uzmanı portresi' },
  { file: 'ekip-4.jpg', id: '1607746882042-944635dfe10e', w: 900, h: 900, faces: true, alt: 'Güzellik uzmanı portresi' },

  // --- Detay / atmosfer -------------------------------------------------
  { file: 'detay-firca.jpg', id: '1526045478516-99145907023c', w: 1200, h: 900, alt: 'Makyaj fırçaları' },
  { file: 'detay-urun.jpg', id: '1608248543803-ba4f8c70ae0b', w: 1200, h: 900, alt: 'Saç bakım ürünü' },
  { file: 'detay-kozmetik.jpg', id: '1571875257727-256c39da42af', w: 1200, h: 900, alt: 'Çiçeklerle kozmetik düzeni' },
  { file: 'detay-palet.jpg', id: '1512496015851-a90fb38ba796', w: 1200, h: 900, alt: 'Far paleti ve makyaj ürünleri' },
]);

/** Unsplash CDN URL'i kurar. */
function buildUrl({ id, w, h, faces }) {
  const params = new URLSearchParams({
    auto: 'format',
    fit: 'crop',
    w: String(w),
    q: '82',
  });
  if (h) params.set('h', String(h));
  if (faces) params.set('crop', 'faces,entropy');
  return `${CDN}${id}?${params}`;
}

async function exists(p) {
  try {
    await access(p);
    return true;
  } catch {
    return false;
  }
}

/** Tek fotoğrafı indirir; ağ hatasında 2 kez daha dener. */
async function download(def) {
  const target = path.join(OUT_DIR, def.file);

  if (!FORCE && (await exists(target))) {
    return { file: def.file, status: 'atlandı' };
  }

  let lastError;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const response = await fetch(buildUrl(def), {
        signal: AbortSignal.timeout(45_000),
        headers: { 'user-agent': 'salon-appointment-v2/photo-fetch' },
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const bytes = Buffer.from(await response.arrayBuffer());
      if (bytes.length < 5_000) throw new Error(`beklenenden küçük dosya (${bytes.length} B)`);

      await writeFile(target, bytes);
      return { file: def.file, status: 'indirildi', kb: Math.round(bytes.length / 1024) };
    } catch (error) {
      lastError = error;
      if (attempt < 3) await new Promise((r) => setTimeout(r, attempt * 800));
    }
  }
  return { file: def.file, status: 'HATA', error: String(lastError) };
}

/** İndirilen fotoğrafların kaynak künyesini yazar. */
async function writeCredits(results) {
  const ok = new Set(results.filter((r) => r.status !== 'HATA').map((r) => r.file));
  const rows = PHOTOS.filter((p) => ok.has(p.file))
    .map((p) => `| \`${p.file}\` | ${p.alt} | https://unsplash.com/photos/${p.id} |`)
    .join('\n');

  const body = `# Fotoğraf künyesi

Bu klasördeki fotoğraflar [Unsplash](https://unsplash.com) üzerinden
**Unsplash License** ile alınmıştır: ticari kullanım dahil ücretsizdir,
atıf zorunlu değildir. Yine de kaynaklar aşağıda listelenmiştir.

Fotoğraflar depoda versiyonlanmaz; \`npm run photos\` ile indirilir.
Kendi fotoğrafını koymak için aynı adla dosyayı bu klasöre bırakman
yeterlidir — betik var olan dosyanın üzerine yazmaz.

| Dosya | İçerik | Kaynak |
| --- | --- | --- |
${rows}
`;
  await writeFile(path.join(OUT_DIR, 'CREDITS.md'), body, 'utf8');
}

async function main() {
  await mkdir(OUT_DIR, { recursive: true });

  console.log(`→ ${PHOTOS.length} fotoğraf hedefleniyor: public/photos/`);

  // Ağı boğmadan 4'erli gruplar hâlinde indir.
  const results = [];
  for (let i = 0; i < PHOTOS.length; i += 4) {
    const batch = await Promise.all(PHOTOS.slice(i, i + 4).map(download));
    for (const r of batch) {
      const suffix = r.kb ? ` (${r.kb} KB)` : r.error ? ` — ${r.error}` : '';
      console.log(`   ${r.status.padEnd(10)} ${r.file}${suffix}`);
    }
    results.push(...batch);
  }

  await writeCredits(results);

  const failed = results.filter((r) => r.status === 'HATA');
  const saved = results.filter((r) => r.status === 'indirildi').length;
  console.log(
    `\n✓ ${saved} yeni fotoğraf, ${results.length - saved - failed.length} zaten vardı` +
      (failed.length ? `, ${failed.length} başarısız` : ''),
  );

  if (failed.length) {
    console.log('  (Eksik fotoğraflar için site çizilmiş illüstrasyona düşer.)');
  }

  // Ağ tamamen kapalıysa bile kurulum akışı kırılmasın.
  process.exit(0);
}

main().catch((error) => {
  console.error('Fotoğraflar indirilemedi:', error);
  process.exit(0);
});
