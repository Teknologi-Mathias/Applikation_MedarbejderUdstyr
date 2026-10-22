; IN-BASE – Windows-installer (Inno Setup 6 eller 7)
;
; Bygges af scripts\build_windows.ps1, som sender versionen (fra app\__init__.py)
; og stierne med:
;   ISCC.exe /DAppVersion=<version> /DSourceDir=<dist\IN-BASE> /DOutputDir=<release> installer\IN-BASE.iss
;
; Bevidst:
; - AppId er FAST for alle versioner (så en ny version opgraderer den gamle).
;   MÅ ALDRIG ÆNDRES.
; - Installerer pr. bruger uden administratorrettigheder (kan vælges for alle).
; - Konfigurationen (%APPDATA%\IN-BASE\.env) og lokale data
;   (%LOCALAPPDATA%\IN-BASE) røres hverken ved installation, opgradering eller
;   afinstallation. Installeren kender intet til Supabase og ændrer ingen data.

#ifndef AppVersion
  #error "AppVersion mangler. Byg med scripts\build_windows.ps1."
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
PrivilegesRequiredOverridesAllowed=dialog
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

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; Ingen [UninstallDelete]: afinstallation fjerner kun de installerede filer.
; Konfiguration og lokale data slettes kun manuelt (se docs\RELEASE.md).
