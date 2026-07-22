param(
    [int]$WebPort = 7777,
    [int]$ApiPort = 8010,
    [string]$ConfigPath
)

$ErrorActionPreference = "Stop"
$Project = Split-Path -Parent $PSScriptRoot
$Web = Join-Path $Project "web"
if (-not $ConfigPath) { $ConfigPath = Join-Path $Project "config.local.ps1" }
if (-not (Test-Path -LiteralPath $ConfigPath)) {
    throw "Configuracao local ausente. Copie config.example.ps1 para config.local.ps1."
}
. $ConfigPath
if (-not $CatalogoConfig) { throw "config.local.ps1 deve definir `$CatalogoConfig" }

$required = @(
    "LinuxProject", "LinuxDb", "LinuxDbDir", "LinuxPython", "Share",
    "MountPoint", "CredentialsFile", "PublicUrl", "ApiToken", "Uid", "Gid"
)
foreach ($key in $required) {
    if (-not $CatalogoConfig[$key]) { throw "Configuracao obrigatoria ausente: $key" }
}

function Test-Http([string]$Url, [string]$Token = "") {
    try {
        $headers = @{}
        if ($Token) { $headers.Authorization = "Bearer $Token" }
        $response = Invoke-WebRequest $Url -Headers $headers -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Wait-Http([string]$Url, [int]$Seconds = 60, [string]$Token = "") {
    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if (Test-Http $Url $Token) { return }
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "Tempo excedido aguardando $Url"
}

# O compartilhamento nunca e montado com escrita.
$mountPoint = $CatalogoConfig.MountPoint
& wsl.exe -d Ubuntu -u root -- mkdir -p $mountPoint
& wsl.exe -d Ubuntu -- mountpoint -q $mountPoint
if ($LASTEXITCODE -ne 0) {
    $mountOptions = "ro,credentials=$($CatalogoConfig.CredentialsFile)," +
        "uid=$($CatalogoConfig.Uid),gid=$($CatalogoConfig.Gid),iocharset=utf8,vers=3.0"
    & wsl.exe -d Ubuntu -u root -- mount -t cifs $CatalogoConfig.Share $mountPoint -o $mountOptions
    if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel montar o acervo remoto" }
}

# A API le uma copia local: SQLite em /mnt/c fica muito lento apos reinicios.
$linuxDb = $CatalogoConfig.LinuxDb
$linuxDbDir = $CatalogoConfig.LinuxDbDir
$linuxProject = $CatalogoConfig.LinuxProject
$linuxPython = $CatalogoConfig.LinuxPython
$apiToken = $CatalogoConfig.ApiToken
$sync = "set -e; mkdir -p '$linuxDbDir'; " +
    "if [ ! -f '$linuxDb' ] || [ '$linuxProject/catalogo.db' -nt '$linuxDb' ]; then " +
    "cp --preserve=timestamps '$linuxProject/catalogo.db' '$linuxDb'; fi"
& wsl.exe -d Ubuntu -- bash -lc $sync
if ($LASTEXITCODE -ne 0) { throw "Nao foi possivel sincronizar o banco operacional" }

if (-not (Test-Http "http://127.0.0.1:$ApiPort/health" $apiToken)) {
    & wsl.exe -d Ubuntu -- pkill -9 -f scripts/run_api.py 2>$null
    $corsOrigins = "http://localhost:$WebPort,http://127.0.0.1:$WebPort,$($CatalogoConfig.PublicUrl)"
    $apiCommand = "cd '$linuxProject' && CATALOGO_HOST=127.0.0.1 CATALOGO_PORT=$ApiPort " +
        "CATALOGO_DB='$linuxDb' CATALOGO_API_TOKEN='$apiToken' " +
        "CATALOGO_CORS_ORIGINS='$corsOrigins' exec '$linuxPython' scripts/run_api.py"
    Start-Process wsl.exe -ArgumentList @('-d', 'Ubuntu', '--', 'bash', '-lc', $apiCommand) `
        -RedirectStandardOutput (Join-Path $Project "demo-api-$ApiPort.out.log") `
        -RedirectStandardError (Join-Path $Project "demo-api-$ApiPort.err.log") `
        -WindowStyle Hidden | Out-Null
    Wait-Http "http://127.0.0.1:$ApiPort/health" 60 $apiToken
}

if (-not (Test-Http "http://127.0.0.1:$WebPort")) {
    $env:API_INTERNAL_URL = "http://127.0.0.1:$ApiPort"
    $env:CATALOGO_API_TOKEN = $apiToken
    $env:ALLOWED_DEV_ORIGINS = $CatalogoConfig.AllowedDevOrigins
    $env:NEXT_PUBLIC_CATALOGO_LOGO_URL = $CatalogoConfig.LogoUrl
    Start-Process npm.cmd -ArgumentList @('run', 'dev', '--', '-p', "$WebPort", '-H', '0.0.0.0') `
        -WorkingDirectory $Web `
        -RedirectStandardOutput (Join-Path $Web "demo-$WebPort.out.log") `
        -RedirectStandardError (Join-Path $Web "demo-$WebPort.err.log") `
        -WindowStyle Hidden | Out-Null
    Wait-Http "http://127.0.0.1:$WebPort"
}

Wait-Http "http://127.0.0.1:$WebPort/api/health"
Write-Output "Catalogo visual online em $($CatalogoConfig.PublicUrl)"
