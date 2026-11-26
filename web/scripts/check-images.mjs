// The repository is public: source photos must not carry EXIF (GPS, camera, dates), XMP or IPTC.
// Colour profiles (ICC) are fine and kept.
import { readdir } from 'node:fs/promises';
import { extname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const root = fileURLToPath(new URL('..', import.meta.url));
const IMAGE_DIRS = ['src/assets', 'public'];
const RASTER = new Set(['.jpg', '.jpeg', '.png', '.webp', '.avif', '.tif', '.tiff', '.heic']);

async function* walk(dir) {
  let entries;
  try {
    entries = await readdir(dir, { withFileTypes: true });
  } catch (error) {
    if (error.code === 'ENOENT') return;
    throw error;
  }
  for (const entry of entries) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) yield* walk(path);
    else if (RASTER.has(extname(entry.name).toLowerCase())) yield path;
  }
}

const offenders = [];
let checked = 0;
for (const dir of IMAGE_DIRS) {
  for await (const file of walk(join(root, dir))) {
    checked += 1;
    const { exif, xmp, iptc } = await sharp(file).metadata();
    const found = [exif && 'EXIF', xmp && 'XMP', iptc && 'IPTC'].filter(Boolean);
    if (found.length) offenders.push(`${relative(root, file)}: ${found.join(', ')}`);
  }
}

if (offenders.length) {
  console.error(`Metadata found in ${offenders.length} image(s); strip it before committing:\n  ${offenders.join('\n  ')}`);
  process.exit(1);
}
console.log(`check-images: ${checked} image(s), no EXIF/XMP/IPTC.`);
