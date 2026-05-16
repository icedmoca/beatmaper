import { mkdir, writeFile, stat, rename, unlink } from 'node:fs/promises';
import { createWriteStream } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pipeline } from 'node:stream/promises';
import { Readable } from 'node:stream';

/** @type {(s: string) => void} */
let log = (s) => process.stdout.write(s);

const DEFAULT_DATASET = 'icedmoca/beatmapmaker';
const DEFAULT_REV = 'main';

const FILES = [
  {
    hf: 'ranked_pattern_model.json',
    dest: ['models', 'ranked_pattern_model.json'],
    minBytes: 4_000_000,
    label: 'ranked_pattern_model.json (~45MB)',
  },
  {
    hf: 'ranked_spacing_profile.json',
    dest: ['models', 'ranked_spacing_profile.json'],
    minBytes: 32,
    label: 'ranked_spacing_profile.json',
  },
  {
    hf: 'brain/dataset_brain.json',
    dest: ['models', 'brain', 'dataset_brain.json'],
    minBytes: 32,
    label: 'brain/dataset_brain.json',
  },
  {
    hf: 'training_report.json',
    dest: ['models', 'training_report.json'],
    minBytes: 4,
    label: 'training_report.json',
    optional: true,
  },
];

function resolveUrl(dataset, rev, hfPath) {
  const enc = hfPath
    .split('/')
    .map((p) => encodeURIComponent(p))
    .join('/');
  return `https://huggingface.co/datasets/${dataset}/resolve/${rev}/${enc}`;
}

async function fileOk(abs, minBytes) {
  try {
    const s = await stat(abs);
    return s.isFile() && s.size >= minBytes;
  } catch {
    return false;
  }
}

async function atomicWrite(dest, data) {
  const dir = dirname(dest);
  await mkdir(dir, { recursive: true });
  const tmp = `${dest}.download`;
  await writeFile(tmp, data);
  try {
    await rename(tmp, dest);
  } catch {
    await unlink(dest).catch(() => {});
    await rename(tmp, dest);
  }
}

/**
 * Stream download (better for large JSON) with simple % progress.
 * @param {string} url
 * @param {string} dest
 * @param {string} label
 */
async function downloadStream(url, dest, label) {
  const res = await fetch(url, {
    redirect: 'follow',
    headers: { 'User-Agent': 'beatmaper-dataset/1.0 (https://github.com/icedmoca/beatmaper)' },
  });
  if (!res.ok || !res.body) {
    const errText = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText}\n${url}\n${errText.slice(0, 400)}`);
  }
  const total = Number(res.headers.get('content-length')) || 0;
  await mkdir(dirname(dest), { recursive: true });
  const tmp = `${dest}.download`;
  const out = createWriteStream(tmp);
  const input = Readable.fromWeb(res.body);
  let written = 0;
  let lastPct = -1;
  input.on('data', (chunk) => {
    written += chunk.length;
    if (total > 0) {
      const pct = Math.min(99, Math.floor((100 * written) / total));
      if (pct !== lastPct && pct % 5 === 0) {
        lastPct = pct;
        log(`\r  ${label}  ${pct}%`);
      }
    }
  });
  await pipeline(input, out);
  if (total > 0) log(`\r  ${label}  100%\n`);
  else log(`\r  ${label}  done (${written} bytes)\n`);
  try {
    await rename(tmp, dest);
  } catch {
    await unlink(dest).catch(() => {});
    await rename(tmp, dest);
  }
}

async function downloadBuffer(url, dest, label) {
  const res = await fetch(url, {
    redirect: 'follow',
    headers: { 'User-Agent': 'beatmaper-dataset/1.0 (https://github.com/icedmoca/beatmaper)' },
  });
  if (!res.ok) {
    const errText = await res.text().catch(() => '');
    throw new Error(`${res.status} ${res.statusText}\n${url}\n${errText.slice(0, 400)}`);
  }
  const buf = Buffer.from(await res.arrayBuffer());
  log(`  ${label}  (${buf.length} bytes)\n`);
  await atomicWrite(dest, buf);
}

/**
 * @param {string} projectRoot - absolute path to repo root
 * @param {{ log?: (s: string) => void, force?: boolean }} [opts]
 */
export async function ensureDatasetFromHuggingFace(projectRoot, opts = {}) {
  if (opts.log) log = opts.log;
  const force = Boolean(opts.force) || process.env.BEATMAPER_FORCE_DATASET === '1';
  const dataset = process.env.BEATMAPER_HF_DATASET || DEFAULT_DATASET;
  const rev = process.env.BEATMAPER_HF_REV || DEFAULT_REV;

  const todo = [];
  for (const spec of FILES) {
    const dest = join(projectRoot, ...spec.dest);
    if (!force && (await fileOk(dest, spec.minBytes))) continue;
    todo.push({ ...spec, dest, url: resolveUrl(dataset, rev, spec.hf) });
  }

  if (todo.length === 0) {
    log('\n\x1b[2mHugging Face dataset files already present; skipping download.\x1b[0m\n');
    return;
  }

  log(`\n\x1b[1mbeatmaper\x1b[0m — fetching dataset \x1b[1m${dataset}\x1b[0m (rev ${rev}) …\n\n`);

  for (const item of todo) {
    log(`  → ${item.label}\n`);
    try {
      if (item.hf === 'ranked_pattern_model.json') {
        await downloadStream(item.url, item.dest, item.label);
      } else {
        await downloadBuffer(item.url, item.dest, item.label);
      }
      if (!(await fileOk(item.dest, item.minBytes))) {
        throw new Error(`File too small or missing after download: ${item.dest}`);
      }
    } catch (e) {
      if (item.optional) {
        log(`  \x1b[33m(skip)\x1b[0m ${item.label}: ${/** @type {Error} */ (e).message}\n`);
        continue;
      }
      throw e;
    }
  }

  log('\n\x1b[32mHugging Face dataset installed under models/.\x1b[0m\n');
}

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const isCli = resolve(process.argv[1] || '') === resolve(fileURLToPath(import.meta.url));

if (isCli) {
  ensureDatasetFromHuggingFace(root).catch((err) => {
    console.error('\n\x1b[31mDataset download failed:\x1b[0m', err.message || err);
    console.error(
      '\nTip: check your network, or set HF_TOKEN for higher rate limits.\n' +
        'Re-run: npm run fetch-dataset\n',
    );
    process.exit(1);
  });
}
