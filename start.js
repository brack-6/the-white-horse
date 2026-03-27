#!/usr/bin/env node

/**
 * White Horse Startup Script
 * Starts both Node.js proxy and Python backend
 */

import { spawn } from 'child_process';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

console.log('🍺 Starting The White Horse...\n');

// Start Python backend
const python = spawn('python', ['app.py'], {
  cwd: __dirname,
  stdio: 'pipe',
  env: { ...process.env }
});

python.stdout.on('data', (data) => {
  console.log(`[Python] ${data.toString().trim()}`);
});

python.stderr.on('data', (data) => {
  console.error(`[Python Error] ${data.toString().trim()}`);
});

// Start Node.js proxy (delayed to ensure Python is ready)
setTimeout(() => {
  console.log('\n[Node.js] Starting payment proxy...');
  const node = spawn('node', ['server.js'], {
    cwd: __dirname,
    stdio: 'inherit',
    env: { ...process.env }
  });

  node.on('close', (code) => {
    console.log(`[Node.js] Process exited with code ${code}`);
    python.kill();
  });

  node.on('error', (err) => {
    console.error('[Node.js Error]', err);
    python.kill();
  });
}, 2000);

python.on('close', (code) => {
  console.log(`[Python] Process exited with code ${code}`);
  process.exit(code);
});

python.on('error', (err) => {
  console.error('[Python Error]', err);
  process.exit(1);
});
