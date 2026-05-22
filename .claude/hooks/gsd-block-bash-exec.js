#!/usr/bin/env node
// gsd-hook-version: local
// gsd-block-bash-exec.js — PreToolUse hook: HARD block attempts to use bash execution in this Windows repo.
//
// Why:
// - In this repo/environment, /bin/bash may be missing.
// - When a verification attempt fails due to missing bash, auto-mode safety can flag the task even if later
//   verification reruns pass. This hook prevents the failing attempt from ever being recorded.
//
// What it blocks:
// - gsd_exec runtime=bash (tool input)
// - Any Bash tool command that tries to invoke /bin/bash explicitly
//
// What to do instead:
// - Run verification commands directly via Windows runner (Bash tool executes via CreateProcess).
// - Or use gsd_exec runtime=node to spawn venv\\Scripts\\python.exe and run pytest.

let input = '';
process.stdin.setEncoding('utf8');
process.stdin.on('data', chunk => (input += chunk));
process.stdin.on('end', () => {
  try {
    const data = JSON.parse(input);
    const toolName = data.tool_name;
    const toolInput = data.tool_input || {};

    // Block gsd_exec runtime=bash
    if (toolName === 'gsd_exec') {
      const runtime = String(toolInput.runtime || '').toLowerCase();
      if (runtime === 'bash') {
        const output = {
          decision: 'block',
          reason:
            "This repo is Windows-native; gsd_exec runtime=bash is blocked because /bin/bash may be missing and can trigger auto-mode safety false negatives. " +
            "Use the Windows runner with venv/Scripts/python.exe, or use gsd_exec runtime=node to spawn venv\\\\Scripts\\\\python.exe for verification.",
        };
        process.stdout.write(JSON.stringify(output));
        process.exit(2);
      }
    }

    // Block explicit /bin/bash usage via Bash tool
    if (toolName === 'Bash') {
      const cmd = String(toolInput.command || '');
      if (cmd.includes('/bin/bash')) {
        const output = {
          decision: 'block',
          reason:
            "Explicit /bin/bash invocation is blocked in this Windows repo. Use venv/Scripts/python.exe directly, or use gsd_exec runtime=node to run verification.",
        };
        process.stdout.write(JSON.stringify(output));
        process.exit(2);
      }
    }

    process.exit(0);
  } catch {
    process.exit(0);
  }
});
