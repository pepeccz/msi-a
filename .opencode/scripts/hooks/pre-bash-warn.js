#!/usr/bin/env node
/**
 * Pre-Bash Warning Hook
 * Warns about commands that should run on remote machine
 */

// Commands that typically run on the remote development server
const REMOTE_COMMANDS = [
  "docker-compose",
  "docker compose",
  "npm run dev",
  "npm start",
  "python main.py",
  "uvicorn",
  "alembic upgrade",
  "pytest",
];

// Commands that are always safe locally
const SAFE_COMMANDS = [
  "git",
  "ls",
  "cat",
  "echo",
  "pwd",
  "which",
  "grep",
  "find",
  "ruff format",
  "npx prettier",
];

const run = () => {
  const command = process.argv.slice(2).join(" ");

  if (!command) {
    return;
  }

  // Check if command is in safe list
  const isSafe = SAFE_COMMANDS.some((safe) => command.startsWith(safe));
  if (isSafe) {
    return;
  }

  // Check if command is in remote list
  const isRemote = REMOTE_COMMANDS.some((remote) => command.includes(remote));
  if (isRemote) {
    console.warn(`
[Hook] WARNING: Development Service Command Detected
Command: ${command}

This command typically runs on the REMOTE development server, not locally.
Development environment: Local machine (code editing)
Execution environment: Remote server (docker, services, tests)

If you need to execute this locally, confirm it's intentional.
`);
  }
};

run();
