; Inno Setup script for the Windows installer (CartridgeCalculator-Setup.exe).
; Built in CI after PyInstaller has made dist\CartridgeCalculator.exe:
;   ISCC.exe /DAppVersion=1.4 scripts\windows_installer.iss
; Installs per user (no admin prompt) so the app can save handloads and settings next to the .exe.
; Reinstalling a newer version upgrades in place; my_calibers.csv, my_handloads.csv and
; settings.json are never installed, so upgrades and uninstalls leave them alone.

#ifndef AppVersion
  #define AppVersion "0.0-dev"
#endif

[Setup]
AppId={{0561EDF5-07C9-425D-9A41-3572B678EB12}
AppName=Cartridge Calculator
AppVersion={#AppVersion}
AppPublisher=mrakz03
SourceDir=..
DefaultDirName={localappdata}\Programs\Cartridge Calculator
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=CartridgeCalculator-Setup
UninstallDisplayIcon={app}\CartridgeCalculator.exe
UninstallDisplayName=Cartridge Calculator
CloseApplications=yes
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\CartridgeCalculator.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "data\*.csv"; Excludes: "my_*.csv"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Cartridge Calculator"; Filename: "{app}\CartridgeCalculator.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Cartridge Calculator"; Filename: "{app}\CartridgeCalculator.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\CartridgeCalculator.exe"; Description: "{cm:LaunchProgram,Cartridge Calculator}"; Flags: nowait postinstall skipifsilent
