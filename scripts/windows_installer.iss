; Inno Setup script for the Windows installer (CartridgeCalculator-Setup.exe).
; Built in CI after PyInstaller has made dist\CartridgeCalculator.exe:
;   ISCC.exe /DAppVersion=1.4 scripts\windows_installer.iss
; Installs per user (no admin prompt) so the app can save handloads and settings next to the .exe.
; Reinstalling a newer version upgrades in place: it first removes the data files the old
; version shipped (ammo_*, loads_*, bullets.csv), so files a release drops don't linger.
; my_calibers.csv, my_handloads.csv and settings.json are never touched.
; The app's own updater (Settings > Updates) downloads this installer and runs it with /SILENT.

#ifndef AppVersion
  #define AppVersion "0.0-dev"
#endif

[Setup]
AppId={{0561EDF5-07C9-425D-9A41-3572B678EB12}
AppName=Load Lore
AppVersion={#AppVersion}
AppPublisher=mrakz03
SourceDir=..
DefaultDirName={localappdata}\Programs\Cartridge Calculator
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=CartridgeCalculator-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\CartridgeCalculator.exe
UninstallDisplayName=Load Lore
CloseApplications=yes
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
Type: files; Name: "{app}\ammo_*.csv"
Type: files; Name: "{app}\loads_*.csv"
Type: files; Name: "{app}\bullets.csv"
; NOTICE.md and DISCLAIMER.md were combined into LEGAL.md
Type: files; Name: "{app}\NOTICE.md"
Type: files; Name: "{app}\DISCLAIMER.md"
; shortcuts from before the rename to In Like Flint - Load Lore (install folder and AppId stay the same)
Type: files; Name: "{autoprograms}\Cartridge Calculator.lnk"
Type: files; Name: "{autodesktop}\Cartridge Calculator.lnk"
; shortcuts named "In Like Flint - Load Lore" from before the menu name became just Load Lore (issue #27)
Type: files; Name: "{autoprograms}\In Like Flint - Load Lore.lnk"
Type: files; Name: "{autodesktop}\In Like Flint - Load Lore.lnk"

[Files]
Source: "dist\CartridgeCalculator.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "data\*.csv"; Excludes: "my_*.csv"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "LEGAL.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Load Lore"; Filename: "{app}\CartridgeCalculator.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Load Lore"; Filename: "{app}\CartridgeCalculator.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\CartridgeCalculator.exe"; Description: "{cm:LaunchProgram,Load Lore}"; Flags: nowait postinstall skipifsilent
; the in-app update (Settings > Updates) runs this installer with /SILENT: start the new version after it
Filename: "{app}\CartridgeCalculator.exe"; Flags: nowait; Check: WizardSilent
