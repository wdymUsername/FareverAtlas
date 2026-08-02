param(
    [Parameter(Position = 0)]
    [string]$GameDirectory
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Source = Join-Path $Root "plugin\nyx_farever_external_bridge.lua"
$ConfigFile = Join-Path $Root "nyx_game_dir.conf"
$AppId = "3672400"

function Add-UniquePath {
    param(
        [System.Collections.Generic.List[string]]$List,
        [string]$Path
    )
    if ($Path -and (Test-Path -LiteralPath $Path) -and -not $List.Contains($Path)) {
        $List.Add($Path)
    }
}

function Find-FareverDirectory {
    $steamRoots = [System.Collections.Generic.List[string]]::new()
    Add-UniquePath $steamRoots (Join-Path ${env:ProgramFiles(x86)} "Steam")
    Add-UniquePath $steamRoots (Join-Path $env:ProgramFiles "Steam")
    try {
        Add-UniquePath $steamRoots (
            Get-ItemPropertyValue -Path "HKCU:\Software\Valve\Steam" -Name "SteamPath"
        )
    } catch {}
    try {
        Add-UniquePath $steamRoots (
            Get-ItemPropertyValue `
                -Path "HKLM:\Software\WOW6432Node\Valve\Steam" `
                -Name "InstallPath"
        )
    } catch {}

    foreach ($root in @($steamRoots)) {
        $vdf = Join-Path $root "steamapps\libraryfolders.vdf"
        if (Test-Path -LiteralPath $vdf) {
            $text = Get-Content -LiteralPath $vdf -Raw
            foreach ($match in [regex]::Matches($text, '"path"\s+"([^"]+)"')) {
                Add-UniquePath $steamRoots ($match.Groups[1].Value -replace '\\\\', '\')
            }
        }
    }

    foreach ($root in $steamRoots) {
        $installName = "Farever"
        $manifest = Join-Path $root "steamapps\appmanifest_$AppId.acf"
        if (Test-Path -LiteralPath $manifest) {
            $text = Get-Content -LiteralPath $manifest -Raw
            $match = [regex]::Match($text, '"installdir"\s+"([^"]+)"')
            if ($match.Success) {
                $installName = $match.Groups[1].Value
            }
        }
        $candidate = Join-Path $root "steamapps\common\$installName"
        if (Test-Path -LiteralPath (Join-Path $candidate "Farever.exe")) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

if (-not $GameDirectory -and (Test-Path -LiteralPath $ConfigFile)) {
    $GameDirectory = (Get-Content -LiteralPath $ConfigFile -TotalCount 1).Trim()
}
if (-not $GameDirectory) {
    $GameDirectory = Find-FareverDirectory
}
if (-not $GameDirectory) {
    throw "Farever was not found. Run: .\install_bridge.ps1 'C:\path\to\Farever'"
}

$GameDirectory = $GameDirectory.TrimEnd('\', '/')
if (-not (Test-Path -LiteralPath (Join-Path $GameDirectory "Farever.exe"))) {
    throw "Farever.exe was not found in: $GameDirectory"
}

$TargetDirectory = Join-Path $GameDirectory "data\plugins"
$Target = Join-Path $TargetDirectory "nyx_farever_external_bridge.lua"
$LegacyTarget = Join-Path $TargetDirectory "farever_external_bridge.lua"
New-Item -ItemType Directory -Force -Path $TargetDirectory | Out-Null
if (Test-Path -LiteralPath $LegacyTarget) {
    Remove-Item -LiteralPath $LegacyTarget
}
Copy-Item -LiteralPath $Source -Destination $Target -Force
$utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $ConfigFile,
    $GameDirectory + [Environment]::NewLine,
    $utf8WithoutBom
)

Write-Host "Installed bridge plugin:"
Write-Host "  $Target"
Write-Host "Farever hot-reloads the plugin when the game is running."
