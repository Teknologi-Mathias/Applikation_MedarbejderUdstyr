<#
.SYNOPSIS
    Bygger IN-BASE Klargøring (Android-appen i android\) og lægger den i assets\mdm\.

.DESCRIPTION
    Kør fra projektmappen, når appen i android\ er ændret:
        .\scripts\byg_klargoering_apk.ps1

    Kræver Android Studio (JDK og Android SDK). IN-BASE serverer APK'en til
    telefonen under klargøringen, og kontrolsummen i QR-koden beregnes af
    IN-BASE ud fra filen – så der skal ikke rettes andet efter et nyt byg.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = "Stop"
$rod = Split-Path -Parent $PSScriptRoot
$android = Join-Path $rod "android"

if (-not $env:JAVA_HOME) {
    $jbr = "C:\Program Files\Android\Android Studio\jbr"
    if (-not (Test-Path $jbr)) { throw "JAVA_HOME er ikke sat, og Android Studio's JDK blev ikke fundet ($jbr)." }
    $env:JAVA_HOME = $jbr
}
$lokal = Join-Path $android "local.properties"
if (-not (Test-Path $lokal)) {
    $sdk = Join-Path $env:LOCALAPPDATA "Android\Sdk"
    if (-not (Test-Path $sdk)) { throw "Android SDK blev ikke fundet ($sdk). Åbn Android Studio én gang." }
    "sdk.dir=$($sdk -replace '\\', '/')" | Set-Content -Encoding ascii $lokal
}

Push-Location $android
try {
    # Gradle/javac skriver advarsler på stderr – det må ikke stoppe scriptet (PowerShell 5.1).
    $ErrorActionPreference = "Continue"
    & .\gradlew.bat assembleRelease --console=plain
    $kode = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($kode -ne 0) { throw "Gradle-bygget mislykkedes." }
} finally {
    Pop-Location
}

$apk = Join-Path $android "app\build\outputs\apk\release\app-release.apk"
$maal = Join-Path $rod "assets\mdm"
New-Item -ItemType Directory -Force $maal | Out-Null
Copy-Item $apk (Join-Path $maal "inbase-klargoering.apk") -Force
$hash = (Get-FileHash (Join-Path $maal "inbase-klargoering.apk") -Algorithm SHA256).Hash
Write-Host "OK: assets\mdm\inbase-klargoering.apk (SHA-256 $hash)"
