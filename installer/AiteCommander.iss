#define MyAppName "Aite Commander"
#define MyAppExeName "AiteCommander.exe"
#define MyAppVersion "1.1.8"
#define MyAppPublisher "Codebdbd"
#define MyAppURL "https://github.com/codebdbd/aitecommander"
#define MyAppDistDir "..\dist\AiteCommander"

[Setup]
AppId={{3D53DB6C-9E14-48D8-BAF7-2C5F1BC016DA}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
OutputDir=..\dist\installer
OutputBaseFilename=AiteCommander-Setup-{#MyAppVersion}
SetupIconFile=..\app\resources\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MyAppDistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: files; Name: "{app}\_internal\app\resources\qss\high_contrast.qss"
Type: filesandordirs; Name: "{app}\_internal\app\resources\themes\high_contrast"
Type: filesandordirs; Name: "{app}\_internal\app\resources\ui_icons\high_contrast"
Type: files; Name: "{app}\_internal\app\resources\qss\pink_pop.qss"
Type: filesandordirs; Name: "{app}\_internal\app\resources\themes\pink_pop"
Type: filesandordirs; Name: "{app}\_internal\app\resources\ui_icons\pink_pop"
Type: files; Name: "{app}\_internal\app\resources\qss\dreamy_room.qss"
Type: filesandordirs; Name: "{app}\_internal\app\resources\themes\dreamy_room"
Type: filesandordirs; Name: "{app}\_internal\app\resources\ui_icons\dreamy_room"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Classes\.aitesec"; ValueType: string; ValueName: ""; ValueData: "AiteCommander.Section"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\AiteCommander.Section"; ValueType: string; ValueName: ""; ValueData: "AiteCommander Section"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AiteCommander.Section\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\_internal\app\resources\package_icon.ico,0"
Root: HKCU; Subkey: "Software\Classes\AiteCommander.Section\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\.aitecat"; ValueType: string; ValueName: ""; ValueData: "AiteCommander.Category"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\AiteCommander.Category"; ValueType: string; ValueName: ""; ValueData: "AiteCommander Category"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AiteCommander.Category\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\_internal\app\resources\package_icon.ico,0"
Root: HKCU; Subkey: "Software\Classes\AiteCommander.Category\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""
Root: HKCU; Subkey: "Software\Classes\.aitepack"; ValueType: string; ValueName: ""; ValueData: "AiteCommander.Package"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\AiteCommander.Package"; ValueType: string; ValueName: ""; ValueData: "AiteCommander Package"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\AiteCommander.Package\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\_internal\app\resources\package_icon.ico,0"
Root: HKCU; Subkey: "Software\Classes\AiteCommander.Package\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""


