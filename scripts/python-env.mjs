import { existsSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { join } from 'node:path';

const shell = process.platform === 'win32';

/** @param {string} projectRoot */
function venvPython(projectRoot) {
  return process.platform === 'win32'
    ? join(projectRoot, '.venv', 'Scripts', 'python.exe')
    : join(projectRoot, '.venv', 'bin', 'python');
}

/** System interpreter only (no project venv). @returns {string[] | null} */
export function resolveSystemPythonPrefix() {
  const candidates = [['python3'], ['python'], ['py', '-3']];
  for (const parts of candidates) {
    const r = spawnSync(parts[0], [...parts.slice(1), '-c', 'pass'], { stdio: 'ignore', shell });
    if (r.status === 0) return parts;
  }
  return null;
}

/**
 * Prefer `projectRoot/.venv` when present, else system Python.
 * @param {string} projectRoot
 * @returns {string[] | null}
 */
export function resolvePythonPrefix(projectRoot) {
  const vpy = venvPython(projectRoot);
  if (existsSync(vpy)) return [vpy];
  return resolveSystemPythonPrefix();
}

/** Create `projectRoot/.venv` using a system Python if missing. */
export function ensureProjectVenvExists(projectRoot) {
  const vpy = venvPython(projectRoot);
  if (existsSync(vpy)) return true;
  const sys = resolveSystemPythonPrefix();
  if (!sys) return false;
  const r = spawnSync(sys[0], [...sys.slice(1), '-m', 'venv', '.venv'], {
    cwd: projectRoot,
    stdio: 'inherit',
    shell,
  });
  return r.status === 0 && existsSync(vpy);
}

/** @param {string[]} prefix */
export function pythonHasBackendDeps(prefix) {
  const r = spawnSync(prefix[0], [...prefix.slice(1), '-c', 'import uvicorn, fastapi, numpy'], {
    stdio: 'ignore',
    shell,
  });
  return r.status === 0;
}

/**
 * @param {string} projectRoot
 * @param {string[]} prefix
 */
export function pipInstallRequirements(projectRoot, prefix) {
  return spawnSync(
    prefix[0],
    [...prefix.slice(1), '-m', 'pip', 'install', '-r', 'requirements.txt'],
    { cwd: projectRoot, stdio: 'inherit', shell },
  );
}
