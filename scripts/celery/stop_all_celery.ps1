# Остановить все процессы Celery

Write-Host "=" -NoNewline; for ($i=0; $i -lt 59; $i++) { Write-Host "=" -NoNewline }; Write-Host ""
Write-Host "Остановка всех процессов Celery"
Write-Host "=" -NoNewline; for ($i=0; $i -lt 59; $i++) { Write-Host "=" -NoNewline }; Write-Host ""
Write-Host ""

# Найти все процессы Celery
$celeryProcesses = Get-WmiObject Win32_Process | Where-Object {$_.CommandLine -like "*celery*"}

if ($celeryProcesses) {
    Write-Host "Найдено процессов Celery: $($celeryProcesses.Count)"
    Write-Host ""
    
    foreach ($process in $celeryProcesses) {
        $pid = $process.ProcessId
        $cmdLine = $process.CommandLine
        
        Write-Host "Остановка PID $pid"
        Write-Host "  $($cmdLine.Substring(0, [Math]::Min(80, $cmdLine.Length)))..."
        
        try {
            Stop-Process -Id $pid -Force -ErrorAction Stop
            Write-Host "  ✓ Остановлен" -ForegroundColor Green
        } catch {
            Write-Host "  ✗ Ошибка: $_" -ForegroundColor Red
        }
        Write-Host ""
    }
    
    Write-Host "=" -NoNewline; for ($i=0; $i -lt 59; $i++) { Write-Host "=" -NoNewline }; Write-Host ""
    Write-Host "Все процессы Celery остановлены"
    Write-Host "=" -NoNewline; for ($i=0; $i -lt 59; $i++) { Write-Host "=" -NoNewline }; Write-Host ""
} else {
    Write-Host "✓ Процессы Celery не найдены" -ForegroundColor Green
}
