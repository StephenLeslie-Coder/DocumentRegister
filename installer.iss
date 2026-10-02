#define AppName GetEnv("DOCUMENT_REGISTER_NAME")
#define AppVersion GetEnv("DOCUMENT_REGISTER_VERSION")
#if AppName == "" || AppVersion == ""
  #error Build with build-installer.ps1 so name and version come from src/config.py.
#endif

[Setup]
AppId={{F8A81571-204C-4B9B-A3A0-1F1D7A356AA2}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir=dist\installer
OutputBaseFilename=DocumentRegisterSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#AppName}.exe
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} Setup
DisableProgramGroupPage=yes

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "dist\{#AppName}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppName}.exe"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppName}.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppName}.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
