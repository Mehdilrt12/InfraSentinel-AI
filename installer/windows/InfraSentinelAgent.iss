#ifndef MyAppVersion
  #define MyAppVersion "2.0.0"
#endif
#ifndef SourceExe
  #define SourceExe "..\..\agent\dist\InfraSentinelAgent.exe"
#endif

[Setup]
AppId={{88D8B94B-AE17-4A92-90B4-85C0B1313F2C}
AppName=InfraSentinel Agent
AppVersion={#MyAppVersion}
AppPublisher=InfraSentinel AI
VersionInfoVersion={#MyAppVersion}
VersionInfoProductVersion={#MyAppVersion}
DefaultDirName={autopf}\InfraSentinel Agent
DefaultGroupName=InfraSentinel Agent
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=output
OutputBaseFilename=InfraSentinelAgent-{#MyAppVersion}-setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
RestartIfNeededByRun=no
UninstallDisplayIcon={app}\InfraSentinelAgent.exe
UninstallDisplayName=InfraSentinel Agent
CloseApplications=force
MinVersion=10.0

[Files]
Source: "{#SourceExe}"; Flags: dontcopy
Source: "{#SourceExe}"; DestDir: "{app}"; Flags: ignoreversion; AfterInstall: ConfigureAndInstallService

[Dirs]
Name: "{commonappdata}\InfraSentinel"

[UninstallRun]
Filename: "{app}\InfraSentinelAgent.exe"; Parameters: "--wait 30 stop"; Flags: runhidden waituntilterminated skipifdoesntexist; RunOnceId: "StopAgentService"
Filename: "{app}\InfraSentinelAgent.exe"; Parameters: "remove"; Flags: runhidden waituntilterminated skipifdoesntexist; RunOnceId: "RemoveAgentService"

[Code]
var
  AgentPage: TInputQueryWizardPage;
  AgentWasInstalled: Boolean;
  InstallationFailed: Boolean;
  InstallationFailureMessage: String;

function DataDirectory(): String;
begin
  Result := ExpandConstant('{commonappdata}\InfraSentinel');
end;

function ConfigExists(): Boolean;
begin
  Result := FileExists(DataDirectory() + '\config.json');
end;

function ParamValue(const Name: String): String;
begin
  Result := ExpandConstant('{param:' + Name + '|}');
end;

function ServiceExists(): Boolean;
var
  ResultCode: Integer;
begin
  Result := Exec(
    ExpandConstant('{sys}\sc.exe'),
    'query InfraSentinelAgent',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode
  ) and (ResultCode = 0);
end;

function RunAgent(const Parameters: String; var ResultCode: Integer): Boolean;
begin
  Result := Exec(
    ExpandConstant('{app}\InfraSentinelAgent.exe'),
    Parameters,
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
end;

procedure InitializeWizard();
begin
  AgentPage := CreateInputQueryPage(
    wpSelectDir,
    'Configuration de l''agent',
    'Connexion sécurisée au serveur central',
    'Saisissez les informations d''enrôlement. Le jeton est à usage unique et ne sera pas enregistré dans config.json.'
  );
  AgentPage.Add('URL du serveur (HTTPS) :', False);
  AgentPage.Add('Nom de la machine (facultatif) :', False);
  AgentPage.Add('Jeton d''enrôlement (facultatif lors d''une mise à niveau) :', True);
  AgentPage.Values[0] := ParamValue('SERVERURL');
  AgentPage.Values[1] := ParamValue('MACHINENAME');
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = AgentPage.ID) and not WizardSilent then
  begin
    if (Trim(AgentPage.Values[0]) = '') and not ConfigExists() then
    begin
      MsgBox('L''URL du serveur est obligatoire pour une première installation.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    if (Trim(AgentPage.Values[2]) = '') and not ConfigExists() then
    begin
      MsgBox('Le jeton d''enrôlement est obligatoire pour une première installation.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ServerURL: String;
  MachineName: String;
  EnrollmentSource: String;
  EnrollmentCopy: String;
  Parameters: String;
  ResultCode: Integer;
  AclResult: Integer;
  EnrollmentCopied: Boolean;
begin
  Result := '';
  AgentWasInstalled := ServiceExists();

  if WizardSilent then
  begin
    if (Trim(ParamValue('SERVERURL')) = '') and not ConfigExists() then
    begin
      Result := 'Le paramètre /SERVERURL est obligatoire pour une première installation silencieuse.';
      Exit;
    end;
    if (Trim(ParamValue('ENROLLMENTFILE')) = '') and not ConfigExists() then
    begin
      Result := 'Le paramètre /ENROLLMENTFILE est obligatoire pour une première installation silencieuse.';
      Exit;
    end;
  end;

  ForceDirectories(DataDirectory());
  if not Exec(
    ExpandConstant('{sys}\icacls.exe'),
    AddQuotes(DataDirectory()) +
      ' /inheritance:r /grant:r *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F',
    '', SW_HIDE, ewWaitUntilTerminated, AclResult
  ) or (AclResult <> 0) then
  begin
    Result := 'Impossible de protéger le répertoire de données de l''agent.';
    Exit;
  end;

  if WizardSilent then
  begin
    ServerURL := Trim(ParamValue('SERVERURL'));
    MachineName := Trim(ParamValue('MACHINENAME'));
    EnrollmentSource := Trim(ParamValue('ENROLLMENTFILE'));
  end
  else
  begin
    ServerURL := Trim(AgentPage.Values[0]);
    MachineName := Trim(AgentPage.Values[1]);
    EnrollmentSource := '';
  end;

  EnrollmentCopy := ExpandConstant('{tmp}\infrasentinel-enrollment.tmp');
  EnrollmentCopied := False;
  if WizardSilent and (EnrollmentSource <> '') then
  begin
    if not FileExists(EnrollmentSource) then
    begin
      Result := 'Le fichier d''enrôlement indiqué est introuvable.';
      Exit;
    end;
    EnrollmentCopied := CopyFile(EnrollmentSource, EnrollmentCopy, False);
  end
  else if not WizardSilent and (Trim(AgentPage.Values[2]) <> '') then
    EnrollmentCopied := SaveStringToFile(
      EnrollmentCopy,
      Trim(AgentPage.Values[2]),
      False
    );

  if ((EnrollmentSource <> '') or (not WizardSilent and (Trim(AgentPage.Values[2]) <> ''))) and
     not EnrollmentCopied then
  begin
    Result := 'Impossible de préparer le jeton d''enrôlement.';
    Exit;
  end;

  if EnrollmentCopied then
  begin
    if not Exec(
      ExpandConstant('{sys}\icacls.exe'),
      AddQuotes(EnrollmentCopy) +
        ' /inheritance:r /grant:r *S-1-5-18:F *S-1-5-32-544:F',
      '', SW_HIDE, ewWaitUntilTerminated, AclResult
    ) or (AclResult <> 0) then
    begin
      DeleteFile(EnrollmentCopy);
      Result := 'Impossible de protéger le jeton d''enrôlement temporaire.';
      Exit;
    end;
  end;

  Parameters := 'configure --data-dir ' + AddQuotes(DataDirectory());
  if ServerURL <> '' then
    Parameters := Parameters + ' --server-url ' + AddQuotes(ServerURL);
  if MachineName <> '' then
    Parameters := Parameters + ' --machine-name ' + AddQuotes(MachineName);
  if EnrollmentCopied then
    Parameters := Parameters + ' --enrollment-file ' + AddQuotes(EnrollmentCopy) +
      ' --delete-enrollment-file';
  if ParamValue('ALLOWHTTPLOCALHOST') = '1' then
    Parameters := Parameters + ' --allow-http-localhost';

  try
    ExtractTemporaryFile('InfraSentinelAgent.exe');
  except
    DeleteFile(EnrollmentCopy);
    Result := 'Impossible d''extraire le programme de configuration de l''agent.';
    Exit;
  end;

  if not Exec(
    ExpandConstant('{tmp}\InfraSentinelAgent.exe'),
    Parameters,
    ExpandConstant('{tmp}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) or (ResultCode <> 0) then
  begin
    DeleteFile(EnrollmentCopy);
    Result := 'La configuration ou l''enrôlement a échoué (code ' +
      IntToStr(ResultCode) + ').';
    Exit;
  end;

  if AgentWasInstalled then
  begin
    RunAgent('--wait 30 stop', ResultCode);
    Sleep(1000);
  end;
end;

procedure RecordInstallationFailure(const MessageText: String);
begin
  InstallationFailed := True;
  InstallationFailureMessage := MessageText;
  SuppressibleMsgBox(MessageText, mbCriticalError, MB_OK, IDOK);
end;

procedure ConfigureAndInstallService();
var
  ServiceCommand: String;
  ResultCode: Integer;
  AuxiliaryResult: Integer;
begin

  if AgentWasInstalled then
    ServiceCommand := 'update'
  else
    ServiceCommand := 'install';
  if not RunAgent('--startup delayed ' + ServiceCommand, ResultCode) or
     (ResultCode <> 0) then
  begin
    RecordInstallationFailure('Impossible d''enregistrer le service Windows.');
    Exit;
  end;

  Exec(
    ExpandConstant('{sys}\sc.exe'),
    'failure InfraSentinelAgent reset= 86400 actions= restart/5000/restart/15000/restart/60000',
    '', SW_HIDE, ewWaitUntilTerminated, AuxiliaryResult
  );
  Exec(
    ExpandConstant('{sys}\sc.exe'),
    'failureflag InfraSentinelAgent 1',
    '', SW_HIDE, ewWaitUntilTerminated, AuxiliaryResult
  );

  if not RunAgent('--wait 30 start', ResultCode) or (ResultCode <> 0) then
  begin
    if not AgentWasInstalled then
      RunAgent('remove', AuxiliaryResult);
    RecordInstallationFailure('Le service InfraSentinel Agent n''a pas démarré.');
  end;
end;

function GetCustomSetupExitCode(): Integer;
begin
  if InstallationFailed then
    Result := 23
  else
    Result := 0;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = wpFinished) and InstallationFailed then
  begin
    WizardForm.FinishedHeadingLabel.Caption := 'Installation incomplète';
    WizardForm.FinishedLabel.Caption := InstallationFailureMessage;
  end;
end;
