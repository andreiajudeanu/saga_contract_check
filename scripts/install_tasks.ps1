# Porneste automat aplicatia (acelasi lucru ca ruleaza.bat) la fiecare N minute si la logare, in fundal.
# Rulati din folderul proiectului:  powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1
# Oprire:                           powershell -ExecutionPolicy Bypass -File scripts\install_tasks.ps1 -Sterge
param(
    [int]$Minute = 15,
    [switch]$Sterge
)

$nume = "SAGA - verificare facturi"
$vechi = @("SAGA - sincronizare contracte")  # sarcina separata din versiunea anterioara

foreach ($n in @($nume) + $vechi) {
    if (Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $n -Confirm:$false
        Write-Host "Sters: $n"
    }
}
if ($Sterge) { return }

$proiect = Split-Path -Parent $PSScriptRoot
$config = Join-Path $proiect "config.toml"
if (-not (Test-Path $config)) { throw "Lipseste $config (copiati config.example.toml)." }

# pythonw ruleaza fara fereastra; rezultatul se vede in log (folderul "log" din config.toml).
$python = (Get-Command python).Source
$pythonw = Join-Path (Split-Path $python) "pythonw.exe"
if (Test-Path $pythonw) { $python = $pythonw }

$action = New-ScheduledTaskAction -Execute $python `
    -Argument "-m saga_check --config `"$config`"" -WorkingDirectory $proiect
$triggers = @(
    (New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes $Minute)),
    (New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME)
)
# IgnoreNew: daca rularea anterioara nu s-a terminat, nu porneste a doua (evita procesarea dubla).
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask -TaskName $nume -Action $action -Trigger $triggers -Settings $settings -Force | Out-Null
Write-Host "Inregistrat: $nume (la fiecare $Minute minute si la logare), cu $python"
