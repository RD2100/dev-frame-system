// Test script: launch IDE with correct Windows quoting
const { spawn } = require('child_process');
const path = require('path');

const CLI = 'C:\\Program Files (x86)\\Tencent\\微信web开发者工具\\cli.bat';
const PROJECT = 'D:\\FitnessManagement';

// Use cmd.exe to handle the quoting
const cmd = `"${CLI}" auto --project "${PROJECT}" --auto-port 19507`;

console.log('Command:', cmd);

const child = spawn('cmd.exe', ['/c', cmd], {
  stdio: ['ignore', 'pipe', 'pipe'],
  windowsVerbatimArguments: true,
});

let out = '';
let err = '';

child.stdout.on('data', d => {
  out += d.toString();
  process.stdout.write(d);
});

child.stderr.on('data', d => {
  err += d.toString();
  process.stderr.write(d);
});

child.on('close', code => {
  console.log('\nExit code:', code);
  if (code === 0) {
    console.log('IDE started successfully!');
    // Now try connecting
    setTimeout(() => {
      const automator = require('miniprogram-automator');
      automator.connect({ wsEndpoint: 'ws://127.0.0.1:19507' })
        .then(mp => {
          console.log('Connected!');
          return mp.currentPage();
        })
        .then(page => {
          console.log('Page:', page.path);
          return mp.close();
        })
        .then(() => console.log('Done'))
        .catch(e => console.error('Connect error:', e.message));
    }, 5000);
  }
});

child.on('error', e => console.error('Spawn error:', e.message));

// Timeout after 20s
setTimeout(() => {
  console.log('\n[Timeout]');
  child.kill();
}, 20000);
