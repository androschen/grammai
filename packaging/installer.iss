#define AppVersion "0.16.0"
#ifndef AppSource
#define AppSource "..\dist\GrammAI"
#endif
[Setup]
AppId={{761445A4-BFD8-4E29-ACDB-4AD68A5931D5}
AppName=GrammAI
AppVersion={#AppVersion}
AppPublisher=GrammAI
DefaultDirName={localappdata}\Programs\GrammAI
DefaultGroupName=GrammAI
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=GrammAI-Setup-{#AppVersion}
SetupIconFile=..\ui\assets\grammai.ico
UninstallDisplayIcon={app}\GrammAI.exe
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
SetupMutex=GrammAIInstaller

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "{#AppSource}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\GrammAI"; Filename: "{app}\GrammAI.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\GrammAI"; Filename: "{app}\GrammAI.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\GrammAI.exe"; Description: "Launch GrammAI"; Flags: nowait postinstall skipifsilent

; Preferences, retained models and existing saved phrases are intentionally outside {app}.
