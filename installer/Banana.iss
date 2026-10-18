; Inno Setup script — per-user install, no admin rights needed.
#define AppVersion GetEnv("DS_VERSION")
#if AppVersion == ""
  #define AppVersion "1.1.0"
#endif

[Setup]
AppId={{5348C965-6102-4561-87E8-F99A437697F0}
AppName=Banana
AppVersion={#AppVersion}
AppPublisher=Banana
DefaultDirName={localappdata}\Programs\Banana
DefaultGroupName=Banana
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Banana-Setup
SetupIconFile=..\banana\assets\banana.ico
UninstallDisplayIcon={app}\Banana.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Tasks]
Name: "autostart"; Description: "Start Banana when I sign in to Windows"; Flags: checkedonce
Name: "contextmenu"; Description: "Add ""Banana"" to the right-click menu for files"; Flags: checkedonce
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\Banana\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Banana"; Filename: "{app}\Banana.exe"
Name: "{autodesktop}\Banana"; Filename: "{app}\Banana.exe"; Tasks: desktopicon
Name: "{usersendto}\Banana"; Filename: "{app}\Banana.exe"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Banana"; ValueData: """{app}\Banana.exe"" --quiet"; Tasks: autostart; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\*\shell\Banana"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Banana…"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\Banana"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\Banana.exe"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\Banana"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\Banana\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Banana.exe"" ""%1"""; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Banana"; Flags: uninsdeletekey

[Run]
Filename: "{app}\Banana.exe"; Description: "Launch Banana now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM Banana.exe"; Flags: runhidden; RunOnceId: "KillBanana"
