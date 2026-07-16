$ErrorActionPreference = "Stop"

$packageDir = $env:TUTTI_APP_PACKAGE_DIR
$port = $env:TUTTI_APP_PORT
$runtimeDir = $env:TUTTI_APP_RUNTIME_DIR
$dataDir = $env:TUTTI_APP_DATA_DIR
$logDir = $env:TUTTI_APP_LOG_DIR
$nodeBin = $env:TUTTI_APP_NODE

if (-not $port) { throw "TUTTI_APP_PORT is required" }
if (-not $packageDir) { throw "TUTTI_APP_PACKAGE_DIR is required" }
if (-not $runtimeDir) { throw "TUTTI_APP_RUNTIME_DIR is required" }
if (-not $dataDir) { throw "TUTTI_APP_DATA_DIR is required" }
if (-not $logDir) { throw "TUTTI_APP_LOG_DIR is required" }
if (-not $nodeBin) { throw "TUTTI_APP_NODE is required" }

$env:TUTTI_APP_HOST = if ($env:TUTTI_APP_HOST) { $env:TUTTI_APP_HOST } else { "127.0.0.1" }

New-Item -ItemType Directory -Force -Path $runtimeDir, $dataDir, $logDir | Out-Null
Set-Location -LiteralPath $runtimeDir
& $nodeBin "$packageDir/server.js"
