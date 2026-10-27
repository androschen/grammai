#define AppVersion "0.18.0"
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
DisableWelcomePage=no
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableFinishedPage=yes
WizardSizePercent=110
DefaultDialogFontName=Segoe UI
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
Filename: "{app}\GrammAI.exe"; Description: "Launch GrammAI"; Flags: nowait skipifsilent

; Preferences, retained models and existing saved phrases are intentionally outside {app}.

[Messages]
WelcomeLabel1=Welcome to GrammAI.
WelcomeLabel2=Learn languages from real conversations.%n%nInstall the desktop app now. Choose models and check CPU/GPU support on first launch.
SetupAppTitle=GrammAI Setup
InstallingLabel=Installing the desktop app. Model downloads start only after you choose them in GrammAI.

[Code]
var
  InstallLocation: TNewStaticText;
  ChangeLocation: TNewButton;
  DesktopShortcut: TNewCheckBox;

procedure ChangeInstallLocation(Sender: TObject);
var
  Folder: String;
begin
  Folder := WizardDirValue;
  if BrowseForFolder('Choose where to install GrammAI', Folder, False) then
  begin
    WizardForm.DirEdit.Text := Folder;
    InstallLocation.Caption := 'Install location' + #13#10 + Folder;
  end;
end;

procedure InitializeWizard;
begin
  WizardForm.Color := $00F5F7F5;
  WizardForm.WizardBitmapImage.Visible := False;
  WizardForm.WelcomeLabel1.Left := ScaleX(24);
  WizardForm.WelcomeLabel1.Top := ScaleY(18);
  WizardForm.WelcomeLabel1.Width := WizardForm.WelcomePage.ClientWidth - ScaleX(48);
  WizardForm.WelcomeLabel1.Font.Size := 20;
  WizardForm.WelcomeLabel1.Font.Color := $00202B19;
  WizardForm.WelcomeLabel2.Left := ScaleX(24);
  WizardForm.WelcomeLabel2.Top := ScaleY(76);
  WizardForm.WelcomeLabel2.Width := WizardForm.WelcomePage.ClientWidth - ScaleX(48);
  WizardForm.WelcomeLabel2.Height := ScaleY(108);
  WizardForm.WelcomeLabel2.Font.Size := 10;
  InstallLocation := TNewStaticText.Create(WizardForm);
  InstallLocation.Parent := WizardForm.WelcomePage;
  InstallLocation.Left := ScaleX(24);
  InstallLocation.Top := ScaleY(192);
  InstallLocation.Width := WizardForm.WelcomePage.ClientWidth - ScaleX(154);
  InstallLocation.Height := ScaleY(42);
  InstallLocation.AutoSize := False;
  InstallLocation.WordWrap := True;
  InstallLocation.Caption := 'Install location' + #13#10 + WizardDirValue;
  ChangeLocation := TNewButton.Create(WizardForm);
  ChangeLocation.Parent := WizardForm.WelcomePage;
  ChangeLocation.Caption := 'Change';
  ChangeLocation.Left := WizardForm.WelcomePage.ClientWidth - ScaleX(108);
  ChangeLocation.Top := ScaleY(199);
  ChangeLocation.Width := ScaleX(84);
  ChangeLocation.Height := ScaleY(26);
  ChangeLocation.OnClick := @ChangeInstallLocation;
  DesktopShortcut := TNewCheckBox.Create(WizardForm);
  DesktopShortcut.Parent := WizardForm.WelcomePage;
  DesktopShortcut.Left := ScaleX(24);
  DesktopShortcut.Top := ScaleY(251);
  DesktopShortcut.Width := WizardForm.WelcomePage.ClientWidth - ScaleX(48);
  DesktopShortcut.Caption := 'Create desktop shortcut';
  DesktopShortcut.Checked := True;
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := PageID = wpSelectTasks;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  if CurPageID = wpWelcome then
  begin
    if DesktopShortcut.Checked then WizardSelectTasks('desktopicon')
    else WizardSelectTasks('!desktopicon');
  end;
  Result := True;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpWelcome then WizardForm.NextButton.Caption := 'Install && open';
end;
