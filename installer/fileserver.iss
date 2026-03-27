; Inno Setup Script for 63xky FileServer
; Requires Inno Setup 6.x or later

#ifndef MyAppVersion
  #define MyAppVersion "1.4.0"
#endif

#define MyAppName "63xky FileServer"
#define MyAppPublisher "63xky"
#define MyAppURL "https://github.com/kRystalDevv/py-file-server"
#define MyAppExeName "FileServer.exe"

[Setup]
AppId={{B3F7E8A1-5C2D-4A9B-8E6F-1D3C5A7B9E2F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={commonpf32}\63xky\FileServer
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=Output
OutputBaseFilename=FileServerSetup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible or arm64
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Installer
VersionInfoProductName={#MyAppName}

; Allow upgrading without uninstalling first
UsePreviousAppDir=yes
CloseApplications=force

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checked
Name: "startmenuicon"; Description: "Create a Start Menu shortcut"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checked
Name: "installcloudflared"; Description: "Install cloudflared (required for Public mode)"; GroupDescription: "Optional Components:"; Flags: unchecked

[Files]
; Main application files from PyInstaller dist
Source: "..\dist\FileServer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Ensure tools directory exists for cloudflared
Source: "..\installer\post_install.bat"; DestDir: "{app}\tools"; Flags: ignoreversion

[Icons]
; Desktop shortcut - opens Textual TUI in a terminal
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; Comment: "Launch 63xky FileServer"

; Desktop shortcut for tray mode
Name: "{autodesktop}\{#MyAppName} (Tray)"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--tray"; Tasks: desktopicon; Comment: "Launch 63xky FileServer in system tray"

; Start Menu shortcuts
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{group}\{#MyAppName} (Tray Mode)"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--tray"; Tasks: startmenuicon
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"; Tasks: startmenuicon

[Run]
; Optional: install cloudflared after setup
Filename: "{cmd}"; Parameters: "/c ""{app}\tools\post_install.bat"" ""{app}\tools"""; StatusMsg: "Installing cloudflared..."; Tasks: installcloudflared; Flags: runhidden waituntilterminated

; Launch after install
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\{#MyAppExeName}"; Parameters: "--tray"; Description: "Launch in system tray mode"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
; Clean up tools directory (but NOT user data in %APPDATA%)
Type: filesandordirs; Name: "{app}\tools"

[Code]
// Pascal Script: warn user about existing config preservation

function InitializeSetup: Boolean;
begin
  Result := True;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  AppDataDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Create tools directory if it doesn't exist
    AppDataDir := ExpandConstant('{app}\tools');
    if not DirExists(AppDataDir) then
      ForceDirectories(AppDataDir);
  end;
end;

function InitializeUninstall: Boolean;
var
  Msg: String;
begin
  Msg := 'Your settings and shared files in %APPDATA%\63xkyFileServer will NOT be removed.' + #13#10 +
         'To remove them manually, delete that folder after uninstalling.' + #13#10#13#10 +
         'Continue with uninstall?';
  Result := MsgBox(Msg, mbConfirmation, MB_YESNO) = IDYES;
end;
