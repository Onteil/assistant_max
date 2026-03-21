# VPN connection to i-TAT for local development.
#
# Topology:
#   Amnezia (WireGuard) - default route, all internet + ngrok through it.
#   i-TAT PPTP          - only 10.10.0.0/16 subnet, does not touch default route.
#
# IMPORTANT: PPTP uses GRE protocol which may be blocked by Amnezia.
# Workaround: Disconnect Amnezia → Connect PPTP → Reconnect Amnezia → Add route
#
# Usage (run as Administrator):
#   .\scripts\vpn-connect.ps1 connect                    # Auto-detect or create VPN
#   .\scripts\vpn-connect.ps1 connect -VpnName WorkVPN   # Use existing WorkVPN
#   .\scripts\vpn-connect.ps1 disconnect
#   .\scripts\vpn-connect.ps1 status

param(
    [Parameter(Position=0)]
    [ValidateSet("connect", "disconnect", "status")]
    [string]$Command = "status",
    
    [Parameter()]
    [string]$VpnName = ""
)

# Use existing VPN connection name or default
if ($VpnName) {
    $VPN_NAME = $VpnName
} else {
    # Try to find existing i-TAT VPN connection
    $existing = Get-VpnConnection -ErrorAction SilentlyContinue | 
        Where-Object { $_.Name -match "WorkVPN|i-TAT|itat" } |
        Select-Object -First 1
    
    if ($existing) {
        $VPN_NAME = $existing.Name
        Write-Host "Found existing VPN connection: $VPN_NAME" -ForegroundColor Cyan
    } else {
        $VPN_NAME = "i-TAT-Dev"
    }
}
$ITAT_SUBNET  = "10.10.0.0"
$ITAT_MASK    = "255.255.0.0"

# --- Load .env ---
function Load-Env {
    $envFile = Join-Path $PSScriptRoot "..\\.env"
    if (-not (Test-Path $envFile)) {
        Write-Host "Warning: .env file not found at $envFile" -ForegroundColor Yellow
        return
    }
    
    Get-Content $envFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        
        # Skip empty lines and comments
        if (-not $line -or $line.StartsWith('#')) {
            return
        }
        
        # Match: KEY = "value" (with quotes - preserve everything inside)
        if ($line -match '^([A-Z_][A-Z0-9_]*)\s*=\s*"([^"]*)"') {
            $k = $Matches[1]
            $v = $Matches[2]
            if ($v -and $v -notmatch '^\[.*\]$') {
                [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
            }
            return
        }
        
        # Match: KEY = value (without quotes - stop at # or end of line)
        if ($line -match '^([A-Z_][A-Z0-9_]*)\s*=\s*([^#\s]+)') {
            $k = $Matches[1]
            $v = $Matches[2].Trim()
            if ($v -and $v -notmatch '^\[.*\]$') {
                [System.Environment]::SetEnvironmentVariable($k, $v, "Process")
            }
        }
    }
}

function Test-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = [Security.Principal.WindowsPrincipal]$identity
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-VpnStatus {
    if (-not (Get-VpnConnection -Name $VPN_NAME -ErrorAction SilentlyContinue)) {
        return "not_created"
    }
    if (rasdial 2>&1 | Select-String $VPN_NAME) {
        return "connected"
    }
    return "disconnected"
}

function New-VpnIfNeeded {
    $existing = Get-VpnConnection -Name $VPN_NAME -ErrorAction SilentlyContinue
    if ($existing) {
        Write-Host "VPN connection '$VPN_NAME' already exists." -ForegroundColor Cyan
        return
    }

    $host_ = $env:ITAT_VPN_HOST
    if (-not $host_) {
        Write-Host "Error: ITAT_VPN_HOST not set in .env" -ForegroundColor Red
        exit 1
    }

    Write-Host "Creating VPN connection '$VPN_NAME'..." -ForegroundColor Cyan

    Add-VpnConnection `
        -Name                $VPN_NAME `
        -ServerAddress       $host_ `
        -TunnelType          Pptp `
        -AuthenticationMethod MSChapv2 `
        -EncryptionLevel     Optional `
        -SplitTunneling      $true `
        -Force

    Write-Host "VPN created (split tunneling enabled)." -ForegroundColor Green
}

function Add-ItatRoute {
    # Wait for interface to come up
    $vpnIp = $null
    for ($i = 0; $i -lt 10; $i++) {
        $iface = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.InterfaceAlias -like "*$VPN_NAME*" } |
            Select-Object -First 1
        
        if ($iface) {
            $vpnIp = $iface.IPAddress
            break
        }
        Start-Sleep -Milliseconds 500
    }

    if (-not $vpnIp) {
        Write-Host "Warning: VPN interface IP not found, route not added." -ForegroundColor Yellow
        return
    }

    route delete $ITAT_SUBNET mask $ITAT_MASK 2>$null | Out-Null
    route add $ITAT_SUBNET mask $ITAT_MASK $vpnIp -p | Out-Null
    Write-Host "Route added: $ITAT_SUBNET/$ITAT_MASK -> $vpnIp (VPN)" -ForegroundColor Green
}

function Connect-Vpn {
    if (-not (Test-Admin)) {
        Write-Host "Administrator rights required. Restart PowerShell as Administrator." -ForegroundColor Red
        exit 1
    }

    Load-Env

    # Check if Amnezia is active
    $amneziaActive = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.InterfaceAlias -match "WireGuard|Amnezia" }
    
    if ($amneziaActive) {
        Write-Host ""
        Write-Host "WARNING: Amnezia VPN is active!" -ForegroundColor Yellow
        Write-Host "PPTP (GRE protocol) may be blocked by Amnezia tunnel." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Options:" -ForegroundColor Cyan
        Write-Host "  1. Disconnect Amnezia temporarily, connect i-TAT VPN, then reconnect Amnezia" -ForegroundColor White
        Write-Host "  2. Use existing WorkVPN connection (if configured to work with Amnezia)" -ForegroundColor White
        Write-Host ""
        $continue = Read-Host "Continue anyway? (y/n)"
        if ($continue -ne "y") {
            Write-Host "Aborted." -ForegroundColor Yellow
            exit 0
        }
    }

    New-VpnIfNeeded

    if ((Get-VpnStatus) -eq "connected") {
        Write-Host "VPN '$VPN_NAME' already connected." -ForegroundColor Green
        Show-Status
        return
    }

    $login = $env:ITAT_VPN_LOGIN
    $pass = $env:ITAT_VPN_PASSWORD
    
    if (-not $login -or -not $pass) {
        Write-Host "Error: ITAT_VPN_LOGIN or ITAT_VPN_PASSWORD not set in .env" -ForegroundColor Red
        Write-Host "Check that .env contains:" -ForegroundColor Yellow
        Write-Host "  ITAT_VPN_LOGIN = `"your_login`"" -ForegroundColor Yellow
        Write-Host "  ITAT_VPN_PASSWORD = `"your_password`"" -ForegroundColor Yellow
        exit 1
    }

    Write-Host "Connecting to i-TAT VPN..." -ForegroundColor Cyan
    $out = rasdial $VPN_NAME $login $pass 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Connection error: $out" -ForegroundColor Red
        Write-Host ""
        Write-Host "If error 806 (GRE blocked):" -ForegroundColor Yellow
        Write-Host "  1. Disconnect Amnezia VPN" -ForegroundColor White
        Write-Host "  2. Connect i-TAT VPN: rasdial $VPN_NAME $login <password>" -ForegroundColor White
        Write-Host "  3. Reconnect Amnezia VPN" -ForegroundColor White
        Write-Host "  4. Run this script again to add route" -ForegroundColor White
        exit 1
    }

    Add-ItatRoute

    Write-Host ""
    Write-Host "Done:" -ForegroundColor Green
    Write-Host "  Amnezia (WireGuard) - default route, ngrok works" -ForegroundColor Cyan
    Write-Host "  i-TAT PPTP          - only 10.10.0.0/16" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Start application with LOCAL_DEV=true." -ForegroundColor Green
}

function Disconnect-Vpn {
    route delete $ITAT_SUBNET mask $ITAT_MASK 2>$null | Out-Null
    rasdial $VPN_NAME /disconnect 2>&1 | Out-Null
    Write-Host "i-TAT VPN disconnected, route removed." -ForegroundColor Green
}

function Show-Status {
    $status = Get-VpnStatus
    
    $statusText = "unknown"
    $color = "Yellow"
    
    if ($status -eq "connected") {
        $statusText = "connected"
        $color = "Green"
    } elseif ($status -eq "disconnected") {
        $statusText = "disconnected"
        $color = "Yellow"
    } elseif ($status -eq "not_created") {
        $statusText = "not created"
        $color = "Red"
    }
    
    Write-Host "i-TAT VPN '$VPN_NAME': $statusText" -ForegroundColor $color

    # Show default routes to verify Amnezia is in place
    Write-Host ""
    Write-Host "Default routes (0.0.0.0):" -ForegroundColor Cyan
    route print -4 | Select-String "^\s+0\.0\.0\.0\s+0\.0\.0\.0"
    Write-Host ""
    Write-Host "Routes to 10.10.x.x:" -ForegroundColor Cyan
    route print -4 | Select-String "10\.10\."
}

# --- Entry point ---
switch ($Command) {
    "connect"    { Connect-Vpn }
    "disconnect" { Disconnect-Vpn }
    "status"     { Show-Status }
}
