import { spawn, spawnSync } from 'node:child_process';
import * as readline from 'node:readline/promises';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { stdin as input, stdout as output } from 'node:process';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const shell = process.platform === 'win32';

function installDeps() {
  output.write('\n\x1b[1mbeatmaper\x1b[0m — running npm install…\n\n');
  const r = spawnSync('npm', ['install'], { cwd: root, stdio: 'inherit', shell });
  if (r.error) throw r.error;
  if (r.status !== 0) process.exit(r.status ?? 1);
  output.write('\n\x1b[32mDependencies ready.\x1b[0m\n');
}

function runNpmScript(name) {
  const child = spawn('npm', ['run', name], { cwd: root, stdio: 'inherit', shell });
  child.on('exit', (code, signal) => {
    if (signal) process.kill(process.pid, signal);
    else process.exit(code ?? 0);
  });
}

async function main() {
  installDeps();

  const { ensureDatasetFromHuggingFace } = await import('./fetch-hf-dataset.mjs');
  try {
    await ensureDatasetFromHuggingFace(root, { log: (s) => output.write(s) });
  } catch (err) {
    output.write(`\n\x1b[31mCould not download the Hugging Face dataset.\x1b[0m\n${/** @type {Error} */ (err).message || err}\n`);
    output.write(
      '\nCheck your network. For higher rate limits, set HF_TOKEN.\nThen run: \x1b[1mnpm run fetch-dataset\x1b[0m\n',
    );
    process.exit(1);
  }

  const rl = readline.createInterface({ input, output });

  output.write(`
  How do you want to run the app?

    \x1b[1m1\x1b[0m  Local website (Vite — open the URL it prints in your browser)
    \x1b[1m2\x1b[0m  Desktop app (Electron + Vite)

    \x1b[1m0\x1b[0m  Exit

`);

  try {
    while (true) {
      const raw = await rl.question('Enter choice [0–2]: ');
      const choice = raw.trim().toLowerCase();

      if (choice === '0' || choice === 'q' || choice === 'quit' || choice === 'exit') {
        output.write('Goodbye.\n');
        process.exit(0);
      }
      if (choice === '1') {
        output.write('\nStarting local website (npm run dev)…\n\n');
        rl.close();
        runNpmScript('dev');
        return;
      }
      if (choice === '2') {
        output.write('\nStarting desktop app (npm run electron:dev)…\n\n');
        rl.close();
        runNpmScript('electron:dev');
        return;
      }

      output.write('\nInvalid choice. Type 1, 2, or 0.\n');
    }
  } finally {
    if (!rl.closed) rl.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
