/**
 * PWA simgelerini `public/icons/icon.svg` kaynağından üretir.
 *
 *   cd frontend && npm run icons
 *
 * `sharp` Next.js ile birlikte gelir (görsel optimizasyonu için);
 * ayrıca kurulması gerekmez. Üretilen PNG'ler depoya eklenir — derleme
 * sırasında çalıştırılmaz.
 *
 *  - icon-*.png      : "any" amaçlı, yuvarlatılmış köşeli simge
 *  - maskable-*.png  : Android uyarlanabilir simge. Zemin kenardan kenara
 *                      taşar, harf %80'lik güvenli alanın içinde kalır.
 *  - apple-touch-icon: iOS köşeleri kendisi yuvarlar → düz kare zemin.
 */
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const outDir = path.join(root, 'public', 'icons');
const source = await readFile(path.join(outDir, 'icon.svg'), 'utf8');

// Köşe yuvarlatması olmayan, tam kare zemin.
const square = source.replace('rx="112"', 'rx="0"');

// Maskelenebilir: içerik %80'e küçültülüp ortalanır, zemin tam kare kalır.
const maskable = square.replace(
  /(<rect[^>]*\/>)([\s\S]*)(<\/svg>)/,
  '$1<g transform="translate(51.2 51.2) scale(0.8)">$2</g>$3',
);

const jobs = [
  { file: 'icon-192.png', svg: source, size: 192 },
  { file: 'icon-512.png', svg: source, size: 512 },
  { file: 'maskable-192.png', svg: maskable, size: 192 },
  { file: 'maskable-512.png', svg: maskable, size: 512 },
  { file: 'apple-touch-icon.png', svg: square, size: 180 },
];

for (const { file, svg, size } of jobs) {
  await sharp(Buffer.from(svg), { density: 384 })
    .resize(size, size)
    .png({ compressionLevel: 9 })
    .toFile(path.join(outDir, file));
  console.log(`✓ public/icons/${file} (${size}×${size})`);
}
