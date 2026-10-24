; Inno Setup script for the Windows installer (LoadLore-v<version>-Setup.exe: CI adds the version
; to dist\LoadLore-Setup.exe). Built in CI after PyInstaller has made dist\LoadLore.exe:
;   ISCC.exe /DAppVersion=1.4 scripts\windows_installer.iss
; Installs per user (no admin prompt) so the app can save handloads and settings next to the .exe.
; Reinstalling a newer version upgrades in place: it first removes the data files the old
; version shipped (ammo_*, loads_*, bullets.csv), so files a release drops don't linger.
; my_calibers.csv, my_handloads.csv and settings.json are never touched.
; The app's own updater (Settings > Updates) downloads this installer and runs it with /SILENT.
; Before the rename (Oct 2026) the app was CartridgeCalculator.exe in ...\Programs\Cartridge Calculator:
; an upgrade moves it to ...\Programs\Load Lore (same AppId, so it stays one app in Settings > Apps),
; brings the user's own files along and then removes the old folder.

#define OldDir "{localappdata}\Programs\Cartridge Calculator"

#ifndef AppVersion
  #define AppVersion "0.0-dev"
#endif

[Setup]
AppId={{0561EDF5-07C9-425D-9A41-3572B678EB12}
AppName=Load Lore
AppVersion={#AppVersion}
AppPublisher=mrakz03
SourceDir=..
DefaultDirName={localappdata}\Programs\Load Lore
; not the folder an older version is in: that one is moved (see [Code])
UsePreviousAppDir=no
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=LoadLore-Setup
SetupIconFile=assets\icon.ico
UninstallDisplayIcon={app}\LoadLore.exe
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
; the program's name before the rename (in case the install folder didn't change)
Type: files; Name: "{app}\CartridgeCalculator.exe"
; shortcuts from before the rename to In Like Flint - Load Lore (install folder and AppId stay the same)
Type: files; Name: "{autoprograms}\Cartridge Calculator.lnk"
Type: files; Name: "{autodesktop}\Cartridge Calculator.lnk"
; shortcuts named "In Like Flint - Load Lore" from before the menu name became just Load Lore (issue #27)
Type: files; Name: "{autoprograms}\In Like Flint - Load Lore.lnk"
Type: files; Name: "{autodesktop}\In Like Flint - Load Lore.lnk"

[Files]
Source: "dist\LoadLore.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "data\*.csv"; Excludes: "my_*.csv"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "LEGAL.md"; DestDir: "{app}"; Flags: ignoreversion
; the user's own files from the pre-rename folder (never replaces one already in the new folder)
Source: "{#OldDir}\my_handloads.csv"; DestDir: "{app}"; Flags: external skipifsourcedoesntexist onlyifdoesntexist uninsneveruninstall
Source: "{#OldDir}\my_calibers.csv"; DestDir: "{app}"; Flags: external skipifsourcedoesntexist onlyifdoesntexist uninsneveruninstall
Source: "{#OldDir}\settings.json"; DestDir: "{app}"; Flags: external skipifsourcedoesntexist onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{autoprograms}\Load Lore"; Filename: "{app}\LoadLore.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Load Lore"; Filename: "{app}\LoadLore.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\LoadLore.exe"; Description: "{cm:LaunchProgram,Load Lore}"; Flags: nowait postinstall skipifsilent
; the in-app update (Settings > Updates) runs this installer with /SILENT: start the new version after it
Filename: "{app}\LoadLore.exe"; Flags: nowait; Check: WizardSilent

[Code]
// once the new copy is in place, remove the pre-rename folder (its user files were copied above)
procedure CurStepChanged(CurStep: TSetupStep);
var
  Old: String;
  Tries: Integer;
begin
  Old := ExpandConstant('{#OldDir}');
  if (CurStep = ssPostInstall) and DirExists(Old) and (CompareText(Old, ExpandConstant('{app}')) <> 0) then
  begin
    // the old app closes itself after starting this installer, but its .exe stays locked
    // until it has: try for up to 10 seconds
    Tries := 0;
    while DirExists(Old) and (Tries < 10) do
    begin
      DelTree(Old, True, True, True);
      if DirExists(Old) then Sleep(1000);
      Tries := Tries + 1;
    end;
    if DirExists(Old) then
      Log('Could not remove all of ' + Old);
  end;
end;
