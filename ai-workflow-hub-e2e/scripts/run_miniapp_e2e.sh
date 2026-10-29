#!/bin/bash
# Miniapp E2E launcher - called from TestFrame pipeline
# Workaround for Windows path encoding issues with Python subprocess

"D:/微信web开发者工具/cli.bat" auto --project "D:/FitnessManagement" --auto-port 19541 --trust-project 2>&1 &
sleep 8
node D:/TestFrame/scripts/run_miniapp_e2e.js 2>&1
