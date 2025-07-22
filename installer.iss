[Setup]
AppName=Turbo Sniper Trader
AppVersion=1.1.0
DefaultDirName={pf}\TurboSniperTrader
DefaultGroupName=Turbo Sniper Trader
OutputDir=.
OutputBaseFilename=TurboInstaller
Compression=lzma
SolidCompression=yes

[Files]
Source: "dist\sniper_gui.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "logo.png"; DestDir: "{app}"; Flags: ignoreversion
Source: "logo.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "Turbo User Manual (v1).pdf"; DestDir: "{app}"; Flags: ignoreversion
Source: "Product Requirements Document.pdf"; DestDir: "{app}"; Flags: ignoreversion
; Add more files as needed, e.g.:
; Source: "settings.json"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Turbo Sniper Trader"; Filename: "{app}\sniper_gui.exe"
Name: "{group}\Turbo User Manual"; Filename: "{app}\Turbo User Manual (v1).pdf"
Name: "{group}\Turbo PRD"; Filename: "{app}\Product Requirements Document.pdf"
Name: "{group}\Uninstall Turbo Sniper Trader"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\sniper_gui.exe"; Description: "Launch Turbo Sniper Trader"; Flags: nowait postinstall skipifsilent 