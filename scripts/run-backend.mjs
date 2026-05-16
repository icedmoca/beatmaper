import { spawn } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { pythonHasBackendDeps, resolvePythonPrefix } from './python-env.mjs';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

const prefix = resolvePythonPrefix(root);
if (!prefix) {
  console.error(
    'No Python 3 interpreter found (tried python3, python, py -3).\nInstall Python 3, then: pip install -r requirements.txt',
  );
  process.exit(1);
}

if (!pythonHasBackendDeps(prefix)) {
  console.error(
    'FastAPI / uvicorn not installed for this Python.\nRun `npm start` once (it installs pip deps) or: pip install -r requirements.txt',
  );
  process.exit(1);
}

const child = spawn(
  prefix[0],
  [...prefix.slice(1), '-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', '8008'],
  { cwd: root, stdio: 'inherit', shell: process.platform === 'win32' },
);

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  else process.exit(code ?? 0);
});
