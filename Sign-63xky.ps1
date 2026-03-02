<# 
Sign-63xky.ps1
Creates or reuses a self-signed code-signing cert, trusts it locally,
signs an EXE with SHA-256 + timestamp, then verifies the signature.
#>

param(
  [Parameter(Mandatory=$true)]
  [string]$ExePath,

  [string]$Subject = "CN=63xkyFileServer",

  # Where to save the exported PFX and CER
  [string]$PfxPath = "$env:USERPROFILE\Desktop\63xkyFileServer.pfx",
  [string]$CerPath = "$env:USERPROFILE\Desktop\63xkyFileServer.cer",

  # If empty, you will be prompted securely
  [string]$PfxPassword = ""
)

function Get-NewestSignTool {
  $paths = Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe' -ErrorAction SilentlyContinue |
           Sort-Object FullName -Descending
  if ($paths.Count -gt 0) { return $paths[0].FullName }
  # Fall back to PATH
  return "signtool.exe"
}

function Ensure-CodeSigningCert {
  param([string]$Subject)

  $cert = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq $Subject } | Select-Object -First 1
  if (-not $cert) {
    Write-Host "No code-signing cert for $Subject. Creating one..."
    $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject $Subject -CertStoreLocation "Cert:\CurrentUser\My"
  } else {
    Write-Host "Using existing cert: $($cert.Thumbprint)"
  }
  return $cert
}

function Export-Certificates {
  param($Cert, [string]$PfxPath, [string]$CerPath, [SecureString]$SecurePwd)

  if (-not (Test-Path $PfxPath)) {
    Write-Host "Exporting PFX -> $PfxPath"
    Export-PfxCertificate -Cert $Cert -FilePath $PfxPath -Password $SecurePwd | Out-Null
  } else {
    Write-Host "PFX already exists: $PfxPath"
  }

  Write-Host "Exporting CER -> $CerPath"
  Export-Certificate -Cert $Cert -FilePath $CerPath | Out-Null
}

function Trust-CertificateLocally {
  param([string]$CerPath)

  Write-Host "Importing CER to CurrentUser\Root"
  Import-Certificate -FilePath $CerPath -CertStoreLocation Cert:\CurrentUser\Root | Out-Null

  Write-Host "Importing CER to CurrentUser\TrustedPublisher"
  Import-Certificate -FilePath $CerPath -CertStoreLocation Cert:\CurrentUser\TrustedPublisher | Out-Null
}

# Main
if (-not (Test-Path $ExePath)) { throw "EXE not found: $ExePath" }
if ([string]::IsNullOrWhiteSpace($PfxPassword)) {
  $securePwd = Read-Host "Enter PFX password" -AsSecureString
  $pwText = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePwd))
} else {
  $pwText = $PfxPassword
  $securePwd = ConvertTo-SecureString $pwText -AsPlainText -Force
}

$cert = Ensure-CodeSigningCert -Subject $Subject
Export-Certificates -Cert $cert -PfxPath $PfxPath -CerPath $CerPath -SecurePwd $securePwd
Trust-CertificateLocally -CerPath $CerPath

$signtool = Get-NewestSignTool
Write-Host "Using signtool: $signtool"

Write-Host "Signing..."
& $signtool sign `
  /fd sha256 `
  /tr http://timestamp.digicert.com `
  /td sha256 `
  /f $PfxPath `
  /p $pwText `
  "$ExePath"

Write-Host "Verifying..."
& $signtool verify /pa /v "$ExePath"
