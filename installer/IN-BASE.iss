; IN-BASE – Windows-installer (Inno Setup 6 eller 7)
;
; Bygges af scripts\build_windows.ps1, som sender versionen (fra app\__init__.py)
; og stierne med:
;   ISCC.exe /DAppVersion=<version> /DSourceDir=<dist\IN-BASE> /DOutputDir=<release>
;            /DKlientKonfig=<build\installer\IN-BASE.env> installer\IN-BASE.iss
;
; Bevidst:
; - AppId er FAST for alle versioner (så en ny version opgraderer den gamle).
;   MÅ ALDRIG ÆNDRES.
; - Installerer altid pr. bruger uden administratorrettigheder, så
;   konfigurationen havner hos den bruger, der installerer.
; - Konfigurationen %APPDATA%\IN-BASE\.env (Supabase-URL + OFFENTLIG
;   publishable-nøgle, lavet af tools\lav_klientkonfig.py) lægges KUN på plads,
;   hvis filen ikke findes. Den overskrives aldrig ved opgradering og slettes
;   ikke ved afinstallation. Den indlejres ikke i IN-BASE.exe.
; - Lokale data (%LOCALAPPDATA%\IN-BASE) røres aldrig. Installeren ændrer intet
;   i Supabase-databasen.
; - Central opdatering: IN-BASE henter selv en ny installer og kører den med
;   /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /OPDATERING=1
;   (app/infrastructure/opdatering.py). /OPDATERING=1 starter IN-BASE igen bagefter.
;   AppMutex = MUTEX i app/ui/enkelt_instans.py.

#ifndef AppVersion
  #error "AppVersion mangler. Byg med scripts\build_windows.ps1."
#endif
#ifndef KlientKonfig
  #error "KlientKonfig mangler (konfigurationen til %APPDATA%\IN-BASE\.env). Byg med scripts\build_windows.ps1."
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\IN-BASE"
#endif
#ifndef OutputDir
  #define OutputDir "..\release"
#endif

#define AppName "IN-BASE"
#define AppExe "IN-BASE.exe"
#define AppPublisher "MASAN"

[Setup]
AppId={{C5BFD02A-D4D8-418F-8093-BC7609B78B60}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
VersionInfoVersion={#AppVersion}
VersionInfoProductVersion={#AppVersion}
VersionInfoDescription={#AppName} installer
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; Ingen administratorkrav: installeres i brugerens egen Programs-mappe.
PrivilegesRequired=lowest
OutputDir={#OutputDir}
OutputBaseFilename=IN-BASE-Setup-v{#AppVersion}
SetupIconFile=..\assets\IN-BASE.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; IN-BASE kan køre i baggrunden ved uret – luk den før filer udskiftes.
CloseApplications=yes
RestartApplications=no
AppMutex=IN-BASE-Instans

[Languages]
Name: "danish"; MessagesFile: "compiler:Languages\Danish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Ved opgradering: fjern den forrige versions biblioteker, så gamle filer ikke
; blandes med nye. Kun inde i installationsmappen – aldrig brugerdata.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Forbindelsen til Supabase: kun hvis brugeren ikke allerede har en konfiguration.
Source: "{#KlientKonfig}"; DestDir: "{userappdata}\IN-BASE"; DestName: ".env"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; Efter en stille opdatering fra IN-BASE selv: start programmet igen.
Filename: "{app}\{#AppExe}"; Flags: nowait; Check: ErOpdatering

; Ingen [UninstallDelete]: afinstallation fjerner kun programfilerne.
; Konfiguration og lokale data slettes kun manuelt (se docs\RELEASE.md).

[Code]
// /OPDATERING=1: installeren er startet af IN-BASE's centrale opdatering.
function ErOpdatering: Boolean;
begin
  Result := ExpandConstant('{param:OPDATERING|0}') = '1';
end;
