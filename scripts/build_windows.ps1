<#
.SYNOPSIS
    Bygger en ny IN-BASE-release: tests -> PyInstaller -> Inno Setup -> SHA-256.

.DESCRIPTION
    Normal brug fra projektmappen:
        .\scripts\build_windows.ps1

    Versionen læses fra app\__init__.py (__version__) og øges ALDRIG automatisk.
    Resultatet lægges i release\ (tidligere versioner slettes ikke):
        release\IN-BASE-Setup-v<version>.exe
        release\IN-BASE-Setup-v<version>.exe.sha256

    Scriptet committer, pusher og tagger ikke, og det rører ikke konfigurationen i
    %APPDATA%\IN-BASE. Det publicerer kun med -Udgiv (pilotkanalen i den centrale
    opdatering) og ændrer aldrig databasens data eller skema.

    Der bygges kun fra en ren arbejdskopi (git status), så en release altid kan
    genskabes fra et commit; commit-hashen står i rapporten og i udgivelsen.

.PARAMETER KlientKonfig
    .env-fil med INBASE_SUPABASE_URL og INBASE_SUPABASE_ANON_KEY, som installeren
    lægger i %APPDATA%\IN-BASE\.env (kun hvis brugeren ikke har en i forvejen).
    Standard: .env i projektmappen. Kun de to værdier kopieres – aldrig testlogin
    eller andre nøgler – og secret-/service_role-nøgler afvises.

.PARAMETER InnoSetupPath
    Fuld sti til ISCC.exe, hvis Inno Setup ikke ligger et almindeligt sted.
    Kan også sættes med miljøvariablen INBASE_ISCC.

.PARAMETER Udgiv
    Udgiv installeren til pilotkanalen i den centrale opdatering bagefter
    (tools\udgiv_version.py udgiv – kræver administrator-login). Kræver en ren
    arbejdskopi. Frigivelse til alle sker bevidst bagefter med "frigiv".

.PARAMETER Noter
    Kort tekst om, hvad der er nyt (vises i opdateringsdialogen). Kun med -Udgiv.

.PARAMETER TilladUcommittet
    Byg selvom der er ucommittede ændringer (kun til afprøvning – kan ikke udgives).

.EXAMPLE
    .\scripts\build_windows.ps1 -InnoSetupPath "D:\Værktøjer\Inno Setup 6\ISCC.exe"

.EXAMPLE
    .\scripts\build_windows.ps1 -Udgiv -Noter "Hurtigere opdatering af listerne"
#>
[CmdletBinding()]
param(
    [string]$KlientKonfig = '',
    [string]$InnoSetupPath = $env:INBASE_ISCC,
    [switch]$Udgiv,
    [string]$Noter = '',
    [switch]$TilladUcommittet
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Rod = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Rod '.venv\Scripts\python.exe'
$Spec = Join-Path $Rod 'MedarbejderUdstyr.spec'
$Iss = Join-Path $Rod 'installer\IN-BASE.iss'
$ArbejdsMappe = Join-Path $Rod 'build\pyinstaller'
$InstallerArbejde = Join-Path $Rod 'build\installer'
$GenereretKonfig = Join-Path $InstallerArbejde 'IN-BASE.env'
if (-not $KlientKonfig) { $KlientKonfig = Join-Path $Rod '.env' }
$DistRod = Join-Path $Rod 'dist'
$AppMappe = Join-Path $DistRod 'IN-BASE'
$ReleaseMappe = Join-Path $Rod 'release'
# Hele den lokale testpakke (ca. 2 min). Docker-/E2E-tests springer selv over (se docs\RELEASE.md).
$TestTekst = 'hele den lokale testpakke'
# Supabase Free: højst 50 MB pr. fil i Storage (central opdatering).
$MaksInstaller = 50MB

$script:Trin = 0
function Trin([string]$Tekst) {
    $script:Trin++
    Write-Host ''
    Write-Host ("[{0}] {1}" -f $script:Trin, $Tekst) -ForegroundColor Cyan
}
function Ok([string]$Tekst) { Write-Host "    OK  $Tekst" -ForegroundColor Green }
function Stop-Build([string]$Tekst) { throw $Tekst }

# Kører et eksternt program. Windows PowerShell 5.1 gør ellers programmets
# stderr-output (fx fra unittest og PyInstaller) til fejl, når output omdirigeres.
# Om kaldet lykkedes, afgøres alene af $LASTEXITCODE.
function Invoke-Native([scriptblock]$Blok) {
    $tidligere = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Blok } finally { $ErrorActionPreference = $tidligere }
}

function Find-Iscc {
    $kandidater = @()
    if ($InnoSetupPath) { $kandidater += $InnoSetupPath }
    foreach ($udgave in @('7', '6')) {
        $kandidater += @(
            (Join-Path $env:ProgramFiles "Inno Setup $udgave\ISCC.exe"),
            (Join-Path ${env:ProgramFiles(x86)} "Inno Setup $udgave\ISCC.exe"),
            (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup $udgave\ISCC.exe")
        )
    }
    foreach ($sti in $kandidater) {
        if ($sti -and (Test-Path -LiteralPath $sti -PathType Leaf)) { return (Resolve-Path -LiteralPath $sti).Path }
    }
    $kommando = Get-Command 'ISCC.exe' -ErrorAction SilentlyContinue
    if ($kommando) { return $kommando.Source }
    if ($InnoSetupPath) { Stop-Build "ISCC.exe findes ikke på den angivne sti: $InnoSetupPath" }
    Stop-Build (@(
        'Inno Setup (version 6 eller 7) blev ikke fundet (ISCC.exe).',
        'Installér det med:  winget install --id JRSoftware.InnoSetup -e',
        'eller hent det fra https://jrsoftware.org/isdl.php.',
        'Ligger det et andet sted, så angiv stien:',
        '  .\scripts\build_windows.ps1 -InnoSetupPath "C:\...\ISCC.exe"'
    ) -join [Environment]::NewLine)
}

$start = Get-Date
try {
    Write-Host '=== IN-BASE release-build ===' -ForegroundColor White

    Trin 'Kontrollerer miljøet'
    if ([Environment]::OSVersion.Platform -ne 'Win32NT') { Stop-Build 'Scriptet skal køres på Windows.' }
    if (-not (Test-Path -LiteralPath $Python)) {
        Stop-Build (@(
            "Det virtuelle Python-miljø mangler: $Python",
            'Opret det fra projektmappen:',
            '  python -m venv .venv',
            '  .venv\Scripts\python.exe -m pip install -r requirements-build.txt'
        ) -join [Environment]::NewLine)
    }
    foreach ($fil in @($Spec, $Iss, (Join-Path $Rod 'main.py'), (Join-Path $Rod 'assets\IN-BASE.ico'))) {
        if (-not (Test-Path -LiteralPath $fil)) { Stop-Build "Påkrævet fil mangler: $fil" }
    }
    Invoke-Native { & $Python -c 'import PySide6, supabase, dotenv, certifi, PyInstaller' }
    if ($LASTEXITCODE -ne 0) {
        Stop-Build (@(
            'Nødvendige Python-pakker mangler i .venv (PySide6, supabase, python-dotenv, PyInstaller).',
            'Installér dem med:',
            '  .venv\Scripts\python.exe -m pip install -r requirements-build.txt'
        ) -join [Environment]::NewLine)
    }
    $Iscc = Find-Iscc
    Ok "Python: $Python"
    Ok "Inno Setup: $Iscc"

    Trin 'Læser versionsnummeret (app\__init__.py)'
    Push-Location $Rod
    try { $Version = ([string](Invoke-Native { & $Python -c 'import app; app.version_tupel(); print(app.__version__)' })).Trim() }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0 -or $Version -notmatch '^\d+\.\d+\.\d+$') {
        Stop-Build "Versionsnummeret i app\__init__.py er ugyldigt ('$Version'). Brug MAJOR.MINOR.PATCH, fx 1.0.0."
    }
    $InstallerNavn = "IN-BASE-Setup-v$Version.exe"
    $Installer = Join-Path $ReleaseMappe $InstallerNavn
    $Erstatter = Test-Path -LiteralPath $Installer
    Ok "Version $Version"
    if ($Erstatter) { Write-Host "    BEMÆRK  $InstallerNavn findes allerede og bliver ERSTATTET." -ForegroundColor Yellow }

    Trin 'Kontrollerer git (en release skal kunne genskabes fra et commit)'
    $Commit = ([string](Invoke-Native { & git -C $Rod rev-parse --short HEAD })).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $Commit) { Stop-Build 'git blev ikke fundet, eller projektmappen er ikke et git-repository.' }
    $Aendringer = ([string](Invoke-Native { & git -C $Rod status --porcelain })).Trim()
    if ($Aendringer) {
        if ($Udgiv) { Stop-Build 'Der er ucommittede ændringer – en sådan build kan ikke udgives. Commit først.' }
        if (-not $TilladUcommittet) {
            Stop-Build (@(
                'Der er ucommittede ændringer (git status). Commit dem først, så releasen kan genskabes,',
                'eller byg med -TilladUcommittet (kun til afprøvning).'
            ) -join [Environment]::NewLine)
        }
        $Commit = "$Commit+ucommittet"
        Write-Host '    BEMÆRK  Bygget med ucommittede ændringer – kun til afprøvning.' -ForegroundColor Yellow
    }
    Ok "Commit $Commit"

    Trin 'Klargør klientkonfigurationen til %APPDATA%\IN-BASE\.env'
    if (Test-Path -LiteralPath $InstallerArbejde) { Remove-Item -LiteralPath $InstallerArbejde -Recurse -Force }
    $SupabaseUrl = ([string](Invoke-Native { & $Python (Join-Path $Rod 'tools\lav_klientkonfig.py') $KlientKonfig $GenereretKonfig })).Trim()
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $GenereretKonfig)) {
        Stop-Build (@(
            "Klientkonfigurationen kunne ikke laves ud fra: $KlientKonfig",
            'Filen skal indeholde:',
            '  INBASE_SUPABASE_URL=https://<projekt-ref>.supabase.co',
            '  INBASE_SUPABASE_ANON_KEY=sb_publishable_<offentlig nøgle>',
            'Angiv evt. en anden fil:  .\scripts\build_windows.ps1 -KlientKonfig <sti>'
        ) -join [Environment]::NewLine)
    }
    Ok "Supabase: $SupabaseUrl (kun URL + publishable-nøgle; kilde: $KlientKonfig)"

    Trin "Kører $TestTekst"
    Push-Location $Rod
    try {
        Invoke-Native { & $Python -m unittest discover -s tests -t . }
        if ($LASTEXITCODE -ne 0) { Stop-Build 'Testene fejlede – der bygges ikke en release.' }
    }
    finally { Pop-Location }
    Ok 'Tests bestået'

    Trin 'Rydder midlertidige buildmapper (release\ røres ikke)'
    foreach ($mappe in @($ArbejdsMappe, $AppMappe)) {
        if (Test-Path -LiteralPath $mappe) { Remove-Item -LiteralPath $mappe -Recurse -Force }
    }
    Ok "Fjernet: build\pyinstaller, dist\IN-BASE"

    Trin 'Bygger applikationen med PyInstaller (onedir)'
    Remove-Item Env:\INBASE_ONEFILE -ErrorAction SilentlyContinue
    Push-Location $Rod
    try {
        Invoke-Native { & $Python -m PyInstaller --noconfirm --clean --log-level WARN `
            --distpath $DistRod --workpath $ArbejdsMappe $Spec }
        if ($LASTEXITCODE -ne 0) { Stop-Build "PyInstaller fejlede (exit $LASTEXITCODE). Se meddelelserne ovenfor." }
    }
    finally { Pop-Location }

    Trin 'Kontrollerer den byggede applikation'
    $Exe = Join-Path $AppMappe 'IN-BASE.exe'
    if (-not (Test-Path -LiteralPath $Exe)) { Stop-Build "IN-BASE.exe blev ikke oprettet: $Exe" }
    foreach ($kraevet in @('_internal\assets\IN-BASE.ico', '_internal\assets\IN-BASE-ikon.svg', '_internal\certifi\cacert.pem')) {
        if (-not (Test-Path -LiteralPath (Join-Path $AppMappe $kraevet))) { Stop-Build "Påkrævet fil mangler i builden: $kraevet" }
    }
    $forbudte = Get-ChildItem -LiteralPath $AppMappe -Recurse -Force | Where-Object {
        $_.Name -like '.env*' -or $_.Name -like '.git*' -or $_.Name -in @(
            'medarbejdere.json', 'arkiv.json', 'onboarding.json', 'onboarding_arkiv.json',
            'brugere.json', 'praeferencer.json', 'test_supabase_connection.py')
    }
    if ($forbudte) { Stop-Build ("Builden indeholder filer, der ikke må distribueres:`n" + ($forbudte.FullName -join "`n")) }
    $filVersion = (Get-Item -LiteralPath $Exe).VersionInfo.ProductVersion
    if ($filVersion -ne $Version) { Stop-Build "IN-BASE.exe har versionen '$filVersion', forventet '$Version'." }
    # Selvtest uden GUI og netværk – med en midlertidig lokal mappe.
    $selvtestMappe = Join-Path $ArbejdsMappe 'selvtest'
    $tidligereLokal = $env:INBASE_LOKAL
    $env:INBASE_LOKAL = $selvtestMappe
    try {
        $proces = Start-Process -FilePath $Exe -ArgumentList '--selvtest' -Wait -PassThru -WindowStyle Hidden
    }
    finally { $env:INBASE_LOKAL = $tidligereLokal }
    if ($proces.ExitCode -ne 0) {
        Stop-Build "Selvtesten af IN-BASE.exe fejlede (exit $($proces.ExitCode)). Se $selvtestMappe\Logs\in-base.log"
    }
    Ok "IN-BASE.exe version $filVersion, assets og certifikater til stede, ingen .env/persondata, selvtest OK"

    Trin 'Bygger installeren med Inno Setup'
    New-Item -ItemType Directory -Force -Path $ReleaseMappe | Out-Null
    Invoke-Native { & $Iscc /Q "/DAppVersion=$Version" "/DSourceDir=$AppMappe" "/DOutputDir=$ReleaseMappe" "/DKlientKonfig=$GenereretKonfig" $Iss }
    if ($LASTEXITCODE -ne 0) { Stop-Build "Inno Setup fejlede (exit $LASTEXITCODE). Se meddelelserne ovenfor." }
    if (-not (Test-Path -LiteralPath $Installer)) { Stop-Build "Installeren blev ikke oprettet: $Installer" }
    if ((Get-Item -LiteralPath $Installer).LastWriteTime -lt $start) { Stop-Build "Installeren blev ikke opdateret: $Installer" }
    $Bytes = (Get-Item -LiteralPath $Installer).Length
    if ($Bytes -gt $MaksInstaller) {
        $Tekst = 'Installeren fylder {0:N1} MB – over 50 MB, som Supabase Free tillader pr. fil (central opdatering).' -f ($Bytes / 1MB)
        if ($Udgiv) { Stop-Build $Tekst }
        Write-Host "    BEMÆRK  $Tekst" -ForegroundColor Yellow
    }
    Ok $InstallerNavn

    Trin 'Beregner SHA-256'
    $hash = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
    $hashFil = "$Installer.sha256"
    # Samme format som sha256sum: "<hash> *<filnavn>"
    [System.IO.File]::WriteAllText($hashFil, "$hash *$InstallerNavn`n", (New-Object System.Text.UTF8Encoding($false)))
    Ok $hash
    # Følgefil til Indstillinger → Opdateringer: hvilket databaseskema pakken kræver og
    # hvilket commit den er bygget fra (siden afviser en pakke, databasen ikke er klar til).
    Push-Location $Rod
    try { $Skema = ([string](Invoke-Native { & $Python -c 'import app; print(app.KRAEVET_SKEMA)' })).Trim() }
    finally { Pop-Location }
    if ($LASTEXITCODE -ne 0 -or $Skema -notmatch '^\d+$') { Stop-Build "KRAEVET_SKEMA i app\__init__.py kunne ikke læses ('$Skema')." }
    $infoFil = "$Installer.json"
    $info = [ordered]@{ version = $Version; kraevet_skema = [int]$Skema; commit = $Commit; sha256 = $hash }
    [System.IO.File]::WriteAllText($infoFil, ($info | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))
    Ok "$InstallerNavn.json (skema $Skema, commit $Commit)"

    if ($Udgiv) {
        Trin 'Udgiver til pilotkanalen (central opdatering)'
        Invoke-Native { & $Python (Join-Path $Rod 'tools\udgiv_version.py') udgiv $Installer --noter $Noter }
        if ($LASTEXITCODE -ne 0) { Stop-Build 'Udgivelsen mislykkedes – installeren ligger i release\ og kan udgives igen med tools\udgiv_version.py.' }
        Ok "Udgivet til pilot. Frigiv til alle: python tools\udgiv_version.py frigiv $Version"
    }

    $stoerrelse = '{0:N1} MB' -f ((Get-Item -LiteralPath $Installer).Length / 1MB)
    $varighed = '{0:mm\:ss}' -f ((Get-Date) - $start)
    Write-Host ''
    Write-Host '=== RELEASE GENNEMFØRT ===' -ForegroundColor Green
    Write-Host "  Version     : $Version$(if ($Erstatter) { '  (erstattede eksisterende build med samme version)' })"
    Write-Host "  Installer   : $Installer ($stoerrelse)"
    Write-Host "  SHA-256     : $hash"
    Write-Host "  Kontrolsum  : $hashFil"
    Write-Host "  App-mappe   : $AppMappe"
    Write-Host "  Supabase    : $SupabaseUrl (lægges i %APPDATA%\IN-BASE\.env, hvis den mangler)"
    Write-Host "  Commit      : $Commit"
    Write-Host "  Tests       : $TestTekst"
    Write-Host "  Varighed    : $varighed"
    if ($Udgiv) { Write-Host '  Udgivet     : pilotkanalen (frigiv bagefter i Indstillinger → Opdateringer)' }
    else { Write-Host '  Udgivet     : nej – træk installeren ind i IN-BASE → Indstillinger → Opdateringer' }
    Write-Host "  Intet er committet eller tagget. Tag gerne commit $($Commit -replace '\+ucommittet$', '') som v$Version i git."
    exit 0
}
catch {
    Write-Host ''
    Write-Host '=== RELEASE IKKE GENNEMFØRT ===' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
