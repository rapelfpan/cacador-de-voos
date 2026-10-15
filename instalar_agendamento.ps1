# Agenda o caçador de voos para rodar às 10h, 14h e 17h40 todos os dias.
# Se o PC estiver desligado no horário, roda assim que ele for ligado.
$pasta  = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python).Source

$acao = New-ScheduledTaskAction -Execute $python -Argument "`"$pasta\buscar_voos.py`"" -WorkingDirectory $pasta
$gatilhos = @(
    New-ScheduledTaskTrigger -Daily -At 10:00
    New-ScheduledTaskTrigger -Daily -At 14:00
    New-ScheduledTaskTrigger -Daily -At 17:40
)
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 20)

Register-ScheduledTask -TaskName "Cacador de Voos Baratos" -Action $acao -Trigger $gatilhos -Settings $config -Force | Out-Null
Write-Host "Agendado: 10h, 14h e 17h40. Para remover: Unregister-ScheduledTask -TaskName 'Cacador de Voos Baratos'"
