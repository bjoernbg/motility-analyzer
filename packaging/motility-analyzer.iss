; Inno Setup script for the Motility Analyzer Windows installer.
;
; Wraps the PyInstaller one-folder build in server/dist/motility-analyzer/.
; One-folder rather than one-file because a one-file build unpacks the whole
; bundle to a temp directory on every launch, which lab users read as a hang.
;
;   cd server && uv run pyinstaller --noconfirm motility-analyzer.spec
;   iscc /DAppVersion=1.0.0 packaging/motility-analyzer.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "Motility Analyzer"
#define AppExe "motility-analyzer.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Motility Analyzer
DefaultDirName={autopf}\MotilityAnalyzer
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; "lowest" keeps the install per-user under %LOCALAPPDATA%\Programs, so lab
; machines need no administrator rights.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist-installer
OutputBaseFilename=MotilityAnalyzer-{#AppVersion}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; The bundled ffmpeg is a GPL build; its license travels with the installer.
LicenseFile=..\server\ffmpeg_bin\windows\LICENSE.txt

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\server\dist\motility-analyzer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; Videos, analyses.db and results live in %LOCALAPPDATA%\MotilityAnalyzer and
; are deliberately left in place on uninstall — they are the user's data.
