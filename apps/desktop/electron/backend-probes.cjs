/**

 * backend-probes.cjs

 *

 * Cheap "does this candidate backend actually work" checks used by

 * resolveClawksisBackend (main.cjs). The resolver walks a ladder of

 * candidates -- bootstrap marker, `clawk` on PATH, system Python with

 * clawk_cli installed -- and historically returned the first candidate

 * whose binary existed on disk. That assumption breaks when a user has

 * a pre-installed Python 3.11-3.13 (so findSystemPython() returns a

 * path) but no clawk_cli in its site-packages: the resolver hands back

 * a backend the spawn step can't actually run, and the user gets a

 * dead-on-arrival "ModuleNotFoundError: No module named 'clawk_cli'"

 * instead of the first-launch installer.

 *

 * These probes give the resolver a way to verify a candidate before

 * trusting it. Failure (non-zero exit, exception, timeout) means "skip

 * this rung, try the next one"; success means "spawn this for real."

 * Falling off the bottom of the ladder lands on the bootstrap-needed

 * sentinel, which is exactly what we want when nothing pre-existing

 * actually works.

 *

 * Both probes are deliberately fast and forgiving:

 *   - 5s timeout (a hung interpreter beats forever, but we still give

 *     slow disks / cold caches room to breathe)

 *   - stdio ignored (we only care about exit code; stdout/stderr are

 *     not surfaced to the user, just to recentClawksisLog for forensics

 *     via the caller's catch block if it chooses)

 *   - any throw -> false (never propagate -- resolver wants a boolean)

 *

 * Kept in a standalone cjs module so it can be unit-tested with

 * `node --test` without dragging in the electron runtime (same pattern

 * as bootstrap-platform.cjs and hardening.cjs).

 */



const { execFileSync } = require('node:child_process')



const PROBE_TIMEOUT_MS = 5000



/**

 * Return true iff `python -c "import clawk_cli"` exits 0.

 *

 * Used to gate the "fallback to system Python with clawk_cli installed"

 * rung of resolveClawksisBackend. Without this, a system Python 3.11-3.13

 * registered in PEP 514 makes findSystemPython() succeed regardless of

 * whether clawk_cli has actually been pip-installed into its

 * site-packages -- and the resolver returns a backend that immediately

 * dies on spawn.

 *

 * @param {string} pythonPath - Absolute path to a python.exe / python.

 * @returns {boolean}

 */

function canImportClawksisCli(pythonPath) {

  if (!pythonPath) return false

  try {

    execFileSync(pythonPath, ['-c', 'import clawk_cli'], {

      stdio: 'ignore',

      timeout: PROBE_TIMEOUT_MS,

      windowsHide: true

    })

    return true

  } catch {

    return false

  }

}



/**

 * Return true iff `<clawkCommand> --version` exits 0.

 *

 * Used to gate the "existing `clawk` on PATH" rung. Without this, a

 * stale clawk.cmd shim left behind by an uninstalled pip install (or

 * a half-built venv whose `clawk` entry-point points at a deleted

 * Python) survives findOnPath() and gets selected as the backend.

 *

 * We intentionally avoid invoking the command with the dashboard args

 * here -- `--version` is the cheapest "is this binary alive" smoke

 * test that every clawk_cli entry-point has supported since 0.1.

 *

 * @param {string} clawkCommand - Resolved absolute path to a clawk

 *   executable (or an interpreter+script wrapper).

 * @param {object} [opts]

 * @param {boolean} [opts.shell] - Whether to run through a shell. For

 *   .cmd/.bat shims on Windows execFileSync needs shell:true to find

 *   the cmd interpreter; mirrors the same flag isCommandScript() drives

 *   in resolveClawksisBackend.

 * @returns {boolean}

 */

function verifyClawksisCli(clawkCommand, opts = {}) {

  if (!clawkCommand) return false

  try {

    execFileSync(clawkCommand, ['--version'], {

      stdio: 'ignore',

      timeout: PROBE_TIMEOUT_MS,

      shell: Boolean(opts.shell),

      windowsHide: true

    })

    return true

  } catch {

    return false

  }

}



module.exports = {

  canImportClawksisCli,

  verifyClawksisCli,

  PROBE_TIMEOUT_MS

}

