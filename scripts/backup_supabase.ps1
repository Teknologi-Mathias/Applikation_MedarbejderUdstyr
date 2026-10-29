<#
.SYNOPSIS
    Sikkerhedskopi af Supabase-databasen + gendannelsestest i en midlertidig Docker-container.

.DESCRIPTION
    Supabase Free tager ingen backup. Dette script (kun for projektets ejer) laver en
    fuld kopi med Supabase CLI og beviser, at den kan gendannes:

      1. Dump: roles.sql, schema.sql, data_public.sql (alle IN-BASE-data, også
         MDM-signeringsnøglen) og data_auth.sql (konti – følsom).
      2. Gendannelsestest: en MIDLERTIDIG PostgreSQL-container (samme hovedversion
         som Supabase) får stubben + alle migreringer (docker\initdb), data_public.sql
         indlæses, og antallet af rækker pr. tabel sammenlignes med dumpet. Fejler
         indlæsningen, afviger produktionens skema fra migreringerne.
      3. manifest.json med kontrolsummer, rækketal og testresultat. De ældste kopier
         ud over -Behold slettes.

    Programmet IN-BASE bruges ikke; udviklingsdatabasen (docker compose) røres ikke.
    Databasens adgangskode skrives aldrig til disk. Mappen indeholder persondata –
    læg den et sted med begrænset adgang (fx krypteret drev).
    Gendannelse til Supabase: docs\SUPABASE_OPSAETNING.md, afsnit 13.

    Kræver: Supabase CLI (supabase) og Docker Desktop.

.PARAMETER Mappe
    Hvor kopierne lægges (der laves en undermappe pr. kørsel). Kan også sættes med
    miljøvariablen INBASE_BACKUP_MAPPE. Der er bevidst ingen standard.

.PARAMETER Behold
    Antal kopier, der beholdes (standard 12).

.EXAMPLE
    .\scripts\backup_supabase.ps1 -Mappe "D:\IN-BASE-backup"
    Forbindelsesstrengen (Supabase Dashboard → Connect → Session pooler) indtastes
    skjult, eller sættes i $env:INBASE_BACKUP_DB_URL for denne PowerShell-session.
#>
[CmdletBinding()]
param(
    [string]$Mappe = $env:INBASE_BACKUP_MAPPE,
    [int]$Behold = 12
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$Rod = Split-Path -Parent $PSScriptRoot
$Container = 'inbase-gendannelsestest'

$script:Trin = 0
function Trin([string]$Tekst) {
    $script:Trin++
    Write-Host ''
    Write-Host ("[{0}] {1}" -f $script:Trin, $Tekst) -ForegroundColor Cyan
}
function Ok([string]$Tekst) { Write-Host "    OK  $Tekst" -ForegroundColor Green }
function Stop-Backup([string]$Tekst) { throw $Tekst }

# Som i build_windows.ps1: stderr fra eksterne programmer er ikke en fejl i sig selv.
function Invoke-Native([scriptblock]$Blok) {
    $tidligere = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & $Blok } finally { $ErrorActionPreference = $tidligere }
}

function Get-Sha256([string]$Sti) { (Get-FileHash -LiteralPath $Sti -Algorithm SHA256).Hash.ToLowerInvariant() }

# Rækker pr. tabel i et data-dump med COPY-blokke ("COPY public.x (...) FROM stdin;" … "\.").
function Get-DumpRaekker([string]$Sti) {
    $antal = [ordered]@{}
    $tabel = $null
    foreach ($linje in [System.IO.File]::ReadLines($Sti)) {
        if ($null -eq $tabel) {
            $m = [regex]::Match($linje, '^COPY\s+"?public"?\."?([A-Za-z0-9_]+)"?\s')
            if ($m.Success) { $tabel = $m.Groups[1].Value; $antal[$tabel] = 0 }
        }
        elseif ($linje -eq '\.') { $tabel = $null }
        else { $antal[$tabel]++ }
    }
    return $antal
}

$DbUrl = $null
$start = Get-Date
try {
    Write-Host '=== IN-BASE backup af Supabase ===' -ForegroundColor White

    Trin 'Kontrollerer værktøjer og backupmappe'
    if (-not (Get-Command 'supabase' -ErrorAction SilentlyContinue)) {
        Stop-Backup 'Supabase CLI blev ikke fundet. Installér den (fx: scoop install supabase) – se docs\SUPABASE_OPSAETNING.md, afsnit 4.'
    }
    Invoke-Native { & docker info --format '{{.ServerVersion}}' } | Out-Null
    if ($LASTEXITCODE -ne 0) { Stop-Backup 'Docker kører ikke. Start Docker Desktop og prøv igen.' }
    if (-not $Mappe) {
        Stop-Backup 'Angiv backupmappen: -Mappe "D:\IN-BASE-backup" (eller $env:INBASE_BACKUP_MAPPE). Mappen indeholder persondata.'
    }
    New-Item -ItemType Directory -Force -Path $Mappe | Out-Null
    $Ud = Join-Path (Resolve-Path -LiteralPath $Mappe).Path (Get-Date -Format 'yyyy-MM-dd_HHmm')
    if (Test-Path -LiteralPath $Ud) { Stop-Backup "Der findes allerede en kopi fra dette minut: $Ud" }
    New-Item -ItemType Directory -Path $Ud | Out-Null
    Ok "Kopien lægges i $Ud"

    Trin 'Forbindelse til databasen (Session pooler-forbindelsesstrengen)'
    $DbUrl = $env:INBASE_BACKUP_DB_URL
    if (-not $DbUrl) {
        $sikker = Read-Host 'Indsæt forbindelsesstrengen (postgresql://...)' -AsSecureString
        $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sikker)
        try { $DbUrl = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
    }
    if ($DbUrl -notmatch '^postgres(ql)?://') { Stop-Backup 'Forbindelsesstrengen skal starte med postgresql://' }
    Ok 'Forbindelsesstreng modtaget (vises og gemmes ikke)'

    Trin 'Dumper roller, skema og data med Supabase CLI'
    $dumps = [ordered]@{
        'roles.sql'       = @('--role-only')
        'schema.sql'      = @()
        'data_public.sql' = @('--data-only', '--use-copy', '--schema', 'public')
        'data_auth.sql'   = @('--data-only', '--use-copy', '--schema', 'auth')
    }
    foreach ($navn in $dumps.Keys) {
        $fil = Join-Path $Ud $navn
        $ekstra = $dumps[$navn]
        Invoke-Native { & supabase db dump --db-url $DbUrl -f $fil @ekstra }
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $fil) -or (Get-Item -LiteralPath $fil).Length -eq 0) {
            Stop-Backup "Dump af $navn mislykkedes (se meddelelserne ovenfor)."
        }
        Ok ("{0} ({1:N0} KB)" -f $navn, ((Get-Item -LiteralPath $fil).Length / 1KB))
    }
    $DataFil = Join-Path $Ud 'data_public.sql'
    $forventet = Get-DumpRaekker $DataFil
    if ($forventet.Count -eq 0) { Stop-Backup 'data_public.sql indeholder ingen tabeller – dumpet er ufuldstændigt.' }
    Ok ("{0} tabeller, {1:N0} rækker i alt" -f $forventet.Count, (($forventet.Values | Measure-Object -Sum).Sum))

    Trin 'Gendannelsestest i en midlertidig container'
    $version = '15'
    $hoved = Get-Content -LiteralPath $DataFil -TotalCount 40 | Where-Object { $_ -match 'Dumped from database version (\d+)' } | Select-Object -First 1
    if ($hoved -and $hoved -match 'Dumped from database version (\d+)') { $version = $Matches[1] }
    Invoke-Native { & docker rm -f $Container 2>$null } | Out-Null
    $kode = [guid]::NewGuid().ToString('N')
    Invoke-Native { & docker run -d --name $Container -e "POSTGRES_PASSWORD=$kode" `
        -v "$Rod\docker\initdb:/docker-entrypoint-initdb.d:ro" `
        -v "$Rod\app\infrastructure\database\migrations:/sql/migrations:ro" `
        -v "$Rod\tests\sql:/sql/tests:ro" -v "${Ud}:/backup:ro" "postgres:$version-alpine" } | Out-Null
    if ($LASTEXITCODE -ne 0) { Stop-Backup "Testcontaineren (postgres:$version-alpine) kunne ikke startes." }
    $klar = $false
    foreach ($forsoeg in 1..90) {
        Start-Sleep -Seconds 2
        $koerer = ([string](Invoke-Native { & docker inspect -f '{{.State.Running}}' $Container })).Trim()
        if ($koerer -ne 'true') { break }
        Invoke-Native { & docker exec $Container pg_isready -h 127.0.0.1 -U postgres } | Out-Null
        if ($LASTEXITCODE -eq 0) { $klar = $true; break }
    }
    if (-not $klar) {
        Invoke-Native { & docker logs --tail 40 $Container }
        Stop-Backup 'Migreringerne kunne ikke køres i testcontaineren (se loggen ovenfor).'
    }
    Ok "PostgreSQL $version med stub og migreringer 001-$((Get-ChildItem "$Rod\app\infrastructure\database\migrations\0*.sql").Count.ToString('000'))"

    # Standarddata fra migreringerne fjernes, så kun backuppens data er tilbage.
    $tom = 'do $x$ declare t text; begin for t in select tablename from pg_tables where schemaname = ''public'' loop execute format(''truncate table public.%I cascade'', t); end loop; end $x$;'
    Invoke-Native { & docker exec -e 'PGOPTIONS=-c client_min_messages=warning' $Container `
        psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q -c $tom }
    if ($LASTEXITCODE -ne 0) { Stop-Backup 'Testdatabasen kunne ikke tømmes før indlæsning.' }
    Invoke-Native { & docker exec -e 'PGOPTIONS=-c session_replication_role=replica' $Container `
        psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q -f /backup/data_public.sql } | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Stop-Backup 'data_public.sql kunne ikke indlæses. Produktionens skema afviger sandsynligvis fra migreringerne (se fejlen ovenfor).'
    }
    # Uden dobbelte anførselstegn: Windows PowerShell 5.1 fjerner dem fra argumenter til
    # eksterne programmer. Tabelnavnene er små bogstaver/tal/_ (se Get-DumpRaekker).
    $sql = ($forventet.Keys | ForEach-Object { "select '$_', count(*) from public.$_" }) -join ' union all '
    $linjer = Invoke-Native { & docker exec $Container psql -U postgres -d postgres -At -F '=' -c $sql }
    if ($LASTEXITCODE -ne 0) { Stop-Backup 'Rækkerne i testdatabasen kunne ikke tælles.' }
    $gendannet = @{}
    foreach ($linje in $linjer) { $del = "$linje".Split('='); if ($del.Count -eq 2) { $gendannet[$del[0]] = [int]$del[1] } }
    $afvigelser = @($forventet.Keys | Where-Object { $gendannet[$_] -ne $forventet[$_] } |
        ForEach-Object { "{0}: dump {1}, gendannet {2}" -f $_, $forventet[$_], $gendannet[$_] })
    if ($afvigelser) { Stop-Backup ("Gendannelsen gav andre rækketal:`n  " + ($afvigelser -join "`n  ")) }
    Ok 'Alle tabeller gendannet med samme antal rækker'

    Trin 'Skriver manifest.json og rydder gamle kopier'
    $filer = Get-ChildItem -LiteralPath $Ud -Filter '*.sql' | ForEach-Object {
        [ordered]@{ navn = $_.Name; bytes = $_.Length; sha256 = (Get-Sha256 $_.FullName) }
    }
    $manifest = [ordered]@{
        tidspunkt = (Get-Date).ToString('s'); postgres = $version; filer = @($filer)
        raekker = $forventet; gendannelsestest = 'OK'
    }
    [System.IO.File]::WriteAllText((Join-Path $Ud 'manifest.json'), ($manifest | ConvertTo-Json -Depth 4),
        (New-Object System.Text.UTF8Encoding($false)))
    $gamle = @(Get-ChildItem -LiteralPath (Split-Path -Parent $Ud) -Directory |
        Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}_\d{4}$' } | Sort-Object Name -Descending |
        Select-Object -Skip ([Math]::Max($Behold, 1)))
    foreach ($gammel in $gamle) { Remove-Item -LiteralPath $gammel.FullName -Recurse -Force }
    Ok ("manifest.json skrevet; {0} gamle kopier slettet (beholder {1})" -f $gamle.Count, $Behold)

    Write-Host ''
    Write-Host '=== BACKUP GENNEMFØRT OG GENDANNELSE AFPRØVET ===' -ForegroundColor Green
    Write-Host "  Kopi      : $Ud"
    Write-Host ("  Varighed  : {0:mm\:ss}" -f ((Get-Date) - $start))
    exit 0
}
catch {
    Write-Host ''
    Write-Host '=== BACKUP IKKE GENNEMFØRT ===' -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
finally {
    $DbUrl = $null
    Invoke-Native { & docker rm -f $Container 2>$null } | Out-Null
}
