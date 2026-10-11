#requires -Version 5.1
<#
.SYNOPSIS
Open foreground, localhost-only SSH tunnels to Jenkins and Argo CD.
.DESCRIPTION
Read current K3s Service addresses over an authenticated SSH connection.
Requires a pre-verified, dedicated known_hosts file. Does not accept new host
keys, read application credentials, alter SSH configuration, or start daemons.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$HostName,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$UserName,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$IdentityFile,
    [Parameter(Mandatory = $true)][ValidateNotNullOrEmpty()][string]$KnownHostsFile,
    [ValidateRange(1, 65535)][int]$Port = 22,
    [ValidateRange(1024, 65535)][int]$JenkinsLocalPort = 18081,
    [ValidateRange(1024, 65535)][int]$ArgoLocalPort = 18443
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-ConnectionTarget {
    param([string]$TargetHost, [string]$TargetUser)
    if ($TargetHost.Length -gt 253 -or $TargetHost -notmatch '^[A-Za-z0-9.-]+$') {
        throw 'HostName must be a DNS name or IPv4 address, without an SSH alias, URL, or options.'
    }
    if ($TargetHost -match '^[0-9.]+$') {
        $null = ConvertTo-CanonicalIPv4 -Address $TargetHost
    }
    else {
        foreach ($label in $TargetHost.Split('.')) {
            if ($label -notmatch '^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$') {
                throw 'HostName contains an invalid DNS label.'
            }
        }
    }
    if ($TargetUser -notmatch '^[A-Za-z_][A-Za-z0-9_.-]{0,63}$') {
        throw 'UserName must be a plain Ubuntu login name.'
    }
}

function ConvertTo-CanonicalIPv4 {
    param([string]$Address)
    $ipv4 = $null
    if ($Address -notmatch '^(?:0|[1-9][0-9]{0,2})(?:\.(?:0|[1-9][0-9]{0,2})){3}$' -or
        -not [Net.IPAddress]::TryParse($Address, [ref]$ipv4) -or
        $ipv4.AddressFamily -ne [Net.Sockets.AddressFamily]::InterNetwork) {
        throw 'Expected a canonical IPv4 address.'
    }
    return $ipv4
}

function Resolve-RequiredLocalFile {
    param([string]$FilePath, [string]$Label)
    if ($FilePath -match '[\x00-\x1f\x7f"%$]' -or $FilePath -notmatch '^[A-Za-z]:[\\/]') {
        throw "$Label must be an absolute local file path, without quotes, control characters, or SSH expansion tokens."
    }
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        throw "$Label does not exist as a file."
    }
    $resolved = Resolve-Path -LiteralPath $FilePath
    if ($resolved.Provider.Name -ne 'FileSystem' -or $resolved.ProviderPath.StartsWith('\\') -or
        ((Get-Item -LiteralPath $resolved.ProviderPath).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "$Label must be a local filesystem file, not a network share or symbolic link."
    }
    return $resolved.ProviderPath
}

function Assert-DedicatedKnownHosts {
    param([string]$FilePath, [string]$LookupHost, [string]$KeygenExecutable)
    $sharedPaths = @()
    if ($env:USERPROFILE) {
        $sharedPaths += Join-Path $env:USERPROFILE '.ssh\known_hosts'
        $sharedPaths += Join-Path $env:USERPROFILE '.ssh\known_hosts2'
    }
    if ($env:ProgramData) {
        $sharedPaths += Join-Path $env:ProgramData 'ssh\ssh_known_hosts'
        $sharedPaths += Join-Path $env:ProgramData 'ssh\ssh_known_hosts2'
    }
    foreach ($sharedPath in $sharedPaths) {
        if ([String]::Equals([IO.Path]::GetFullPath($sharedPath), $FilePath, [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Use a dedicated known_hosts file, not a default user or system trust file.'
        }
    }
    $entries = @()
    foreach ($line in Get-Content -LiteralPath $FilePath -Encoding UTF8) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) { continue }
        $fields = $trimmed -split '\s+', 4
        if ($fields.Count -lt 3 -or $fields[0] -match '[@*!?]' -or
            $fields[1] -notmatch '^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(?:256|384|521))$') {
            throw 'The dedicated known_hosts file must contain explicit, pinned host keys without markers or wildcards.'
        }
        try {
            $keyBytes = [Convert]::FromBase64String($fields[2])
            if ($keyBytes.Length -eq 0) { throw 'Empty key.' }
        }
        catch { throw 'The dedicated known_hosts file contains malformed key data.' }
        $entries += [PSCustomObject]@{ Key = $fields[1] + ' ' + $fields[2] }
    }
    if ($entries.Count -eq 0) { throw 'The dedicated known_hosts file contains no pinned host key.' }
    $keyLookupOutput = @(& $KeygenExecutable '-F' $LookupHost '-f' $FilePath)
    if ($LASTEXITCODE -ne 0) {
        throw 'No verified host key matches this HostName and Port in the dedicated known_hosts file.'
    }
    $matchingKeys = @($keyLookupOutput | Where-Object { $_ -and -not $_.StartsWith('#') } | ForEach-Object {
        $fields = $_ -split '\s+', 4
        if ($fields.Count -ge 3) { $fields[1] + ' ' + $fields[2] }
    })
    foreach ($entry in $entries) {
        if ($matchingKeys -cnotcontains $entry.Key) {
            throw 'The dedicated known_hosts file also trusts a different host key. Use a file dedicated to this server.'
        }
    }
}

function Get-KnownHostsSshOption {
    param([string]$FilePath)
    # OpenSSH needs literal inner quotes around a path that can contain spaces.
    $option = 'UserKnownHostsFile="{0}"' -f $FilePath.Replace('\', '/')
    $nativeMode = Get-Variable -Name 'PSNativeCommandArgumentPassing' -ErrorAction SilentlyContinue
    if ($null -eq $nativeMode -or [string]$nativeMode.Value -eq 'Legacy') {
        # Windows PowerShell / older pwsh remove one quoting layer for native commands.
        return $option.Replace('"', '"""')
    }
    return $option
}

function Get-ValidatedServiceEndpoint {
    param([string]$Json, [string]$ServiceName, [string]$Namespace, [int]$ServicePort)
    try { $service = $Json | ConvertFrom-Json }
    catch { throw "Unable to parse Kubernetes Service JSON for $Namespace/$ServiceName." }
    try {
        if ($service.kind -cne 'Service' -or $service.metadata.name -cne $ServiceName -or
            $service.metadata.namespace -cne $Namespace -or $service.spec.type -cne 'ClusterIP') {
            throw 'Unexpected Service identity or type.'
        }
        $ipv4 = ConvertTo-CanonicalIPv4 -Address $service.spec.clusterIP
        $octets = $ipv4.GetAddressBytes()
        $isPrivate = $octets[0] -eq 10 -or
            ($octets[0] -eq 172 -and $octets[1] -ge 16 -and $octets[1] -le 31) -or
            ($octets[0] -eq 192 -and $octets[1] -eq 168)
        if (-not $isPrivate) { throw 'Service address is not RFC1918 private IPv4.' }
        $matchingPorts = @($service.spec.ports | Where-Object {
            $_.port -is [int] -and $_.port -eq $ServicePort -and $_.protocol -ceq 'TCP'
        })
        if ($matchingPorts.Count -ne 1) { throw 'Expected TCP Service port is missing or ambiguous.' }
        return $ipv4.ToString()
    }
    catch { throw "Service validation failed for $Namespace/$ServiceName (ClusterIP, private IPv4, TCP $ServicePort required)." }
}

function Read-RemoteService {
    param([string]$SshExecutable, [string[]]$SshOptions, [string]$TargetHost,
        [string]$RemoteCommand, [string]$ServiceName, [string]$Namespace, [int]$ServicePort)
    $output = @(& $SshExecutable @SshOptions '-T' $TargetHost $RemoteCommand)
    if ($LASTEXITCODE -ne 0) {
        throw "SSH Service lookup failed for $Namespace/$ServiceName. Check host trust, key authentication, and sudo -n k3s access."
    }
    return Get-ValidatedServiceEndpoint -Json ($output -join "`n") -ServiceName $ServiceName -Namespace $Namespace -ServicePort $ServicePort
}

Assert-ConnectionTarget -TargetHost $HostName -TargetUser $UserName
if ($JenkinsLocalPort -eq $ArgoLocalPort) { throw 'JenkinsLocalPort and ArgoLocalPort must be different.' }
$identityPath = Resolve-RequiredLocalFile -FilePath $IdentityFile -Label 'IdentityFile'
$knownHostsPath = Resolve-RequiredLocalFile -FilePath $KnownHostsFile -Label 'KnownHostsFile'
if ($identityPath.EndsWith('.pub', [StringComparison]::OrdinalIgnoreCase) -or
    [String]::Equals($identityPath, $knownHostsPath, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'IdentityFile must be a private key file, separate from KnownHostsFile.'
}
$sshExecutable = (Get-Command 'ssh.exe' -CommandType Application -ErrorAction Stop | Select-Object -First 1).Source
$keygenExecutable = Join-Path (Split-Path -Parent $sshExecutable) 'ssh-keygen.exe'
if (-not (Test-Path -LiteralPath $keygenExecutable -PathType Leaf)) {
    throw 'ssh-keygen.exe must be installed beside ssh.exe (Windows OpenSSH client).'
}
$lookupHost = $HostName
if ($Port -ne 22) { $lookupHost = '[{0}]:{1}' -f $HostName, $Port }
Assert-DedicatedKnownHosts -FilePath $knownHostsPath -LookupHost $lookupHost -KeygenExecutable $keygenExecutable

$knownHostsOption = Get-KnownHostsSshOption -FilePath $knownHostsPath
$sshOptions = @(
    '-F', 'none', '-i', $identityPath, '-p', [string]$Port, '-l', $UserName,
    '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
    '-o', 'StrictHostKeyChecking=yes', '-o', $knownHostsOption,
    '-o', 'GlobalKnownHostsFile=none', '-o', 'UpdateHostKeys=no',
    '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=3'
)

$jenkinsAddress = Read-RemoteService -SshExecutable $sshExecutable -SshOptions $sshOptions -TargetHost $HostName `
    -RemoteCommand 'sudo -n k3s kubectl get service jenkins --namespace jenkins -o json' `
    -ServiceName 'jenkins' -Namespace 'jenkins' -ServicePort 8080
$argoAddress = Read-RemoteService -SshExecutable $sshExecutable -SshOptions $sshOptions -TargetHost $HostName `
    -RemoteCommand 'sudo -n k3s kubectl get service argocd-server --namespace argocd -o json' `
    -ServiceName 'argocd-server' -Namespace 'argocd' -ServicePort 443

Write-Host ('Jenkins: http://127.0.0.1:{0}' -f $JenkinsLocalPort)
Write-Host ('Argo CD: https://127.0.0.1:{0} (verify its TLS certificate fingerprint before login)' -f $ArgoLocalPort)
Write-Host 'Keep this terminal open. Press Ctrl+C to close both tunnels. No application credentials are read.'
$jenkinsForward = '127.0.0.1:{0}:{1}:8080' -f $JenkinsLocalPort, $jenkinsAddress
$argoForward = '127.0.0.1:{0}:{1}:443' -f $ArgoLocalPort, $argoAddress
& $sshExecutable @sshOptions '-N' '-T' '-o' 'ExitOnForwardFailure=yes' '-L' $jenkinsForward '-L' $argoForward $HostName
if ($LASTEXITCODE -ne 0) { throw 'SSH tunnel ended with a nonzero exit status. Check port conflicts, connectivity, and server forwarding policy.' }
