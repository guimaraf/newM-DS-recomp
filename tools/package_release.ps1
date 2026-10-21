param(
    [string]$Destination = '',
    [string]$Rom = ''
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
if (-not $Destination) {
    $Destination = Join-Path $projectRoot 'dist-release/New Super Mario Bros DS Decomp'
}
if (-not $Rom) {
    $Rom = Join-Path $projectRoot 'dist-playable/New Super Mario Bros. (USA).nds'
}
$Destination = [IO.Path]::GetFullPath($Destination)
if (Test-Path -LiteralPath $Destination) {
    throw "A pasta de destino ja existe: $Destination. Escolha uma pasta nova."
}
if ((Get-FileHash -LiteralPath $Rom -Algorithm SHA1).Hash -ne
    'a22713711b5cd58dfbafc9688dadea66c59888ce') {
    throw 'ROM diferente da variante USA suportada.'
}

# Explicit allowlist: no personal saves, settings, BIOS dumps or diagnostics.
$files = [ordered]@{
    'New Super Mario Bros DS Decomp.exe' = 'build-launcher/New Super Mario Bros DS Decomp.exe'
    'New Super Mario Bros DS Decomp Runner.exe' = 'build-runner/New Super Mario Bros DS Decomp Runner.exe'
    'SDL3.dll' = 'dist-playable/SDL3.dll'
    'libgcc_s_seh-1.dll' = 'dist-playable/libgcc_s_seh-1.dll'
    'libstdc++-6.dll' = 'dist-playable/libstdc++-6.dll'
    'libwinpthread-1.dll' = 'dist-playable/libwinpthread-1.dll'
    'game.toml' = 'game.toml'
}
$assets = @(
    'fonts/LatoLatin-Regular.ttf', 'fonts/LatoLatin-Bold.ttf',
    'fonts/OpenMoji-black-glyf.ttf', 'fonts/NotoSansSymbols2-Regular.ttf',
    'img/brand_mark.tga', 'img/brand_nds.tga', 'img/pad_nds.tga',
    'img/verdict_ok.tga', 'img/verdict_warn.tga', 'img/verdict_bad.tga',
    'img/verdict_none.tga', 'img/boxart.tga'
)
foreach ($asset in $assets) {
    $files["assets/$asset"] = "build-launcher/assets/$asset"
}
foreach ($source in $files.Values) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $source) -PathType Leaf)) {
        throw "Arquivo necessario ausente: $source"
    }
}
New-Item -ItemType Directory -Path $Destination | Out-Null
foreach ($entry in $files.GetEnumerator()) {
    $target = Join-Path $Destination $entry.Key
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $target) | Out-Null
    Copy-Item -LiteralPath (Join-Path $projectRoot $entry.Value) -Destination $target
}
Copy-Item -LiteralPath $Rom -Destination (Join-Path $Destination 'New Super Mario Bros. (USA).nds')
New-Item -ItemType Directory -Path (Join-Path $Destination 'bios') | Out-Null
Write-Output "Release criada: $Destination"
Write-Output 'Abra New Super Mario Bros DS Decomp.exe para jogar.'
