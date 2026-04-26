#!/usr/bin/env node

const { spawnSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const ext = process.platform === 'win32' ? '.exe' : '';
const binPath = path.join(__dirname, `trailsnap${ext}`);

if (!fs.existsSync(binPath)) {
  console.error('Error: trailsnap binary not found. Please reinstall the package.');
  process.exit(1);
}

const args = process.argv.slice(2);
const result = spawnSync(binPath, args, { stdio: 'inherit' });

if (result.error) {
  console.error('Error executing trailsnap:', result.error.message);
  process.exit(1);
}

process.exit(result.status || 0);
