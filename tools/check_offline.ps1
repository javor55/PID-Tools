# M25 – kontrola, že PID Tools nekomunikuje mimo tento počítač.
# Spusťte v PowerShellu PŘED spuštěním aplikace a nechte běžet po celou dobu testu (Ctrl+C ukončí a vypíše souhrn):
#   powershell -ExecutionPolicy Bypass -File tools\check_offline.ps1
# Každé 2 s zapíše TCP spojení procesů pidtools-desktop, pidtools-api a msedgewebview2 (okno aplikace). Spojení na jinou adresu
# než 127.0.0.1 / ::1 se vypíše červeně a na konci je souhrn. WebView2 může při prvním startu mluvit se servery Microsoftu
# (aktualizace runtime) – to není komunikace aplikace; na PC bez sítě se nespojí nikam.
param([int]$IntervalSec = 2)

$names = @("pidtools-desktop", "pidtools-api", "msedgewebview2")
$seen = @{}
$foreign = @{}
Write-Host "Sleduji procesy: $($names -join ', ') (Ctrl+C = konec)" -ForegroundColor Cyan
try {
    while ($true) {
        $procs = Get-Process -ErrorAction SilentlyContinue | Where-Object { $names -contains $_.ProcessName }
        foreach ($p in $procs) {
            $conns = Get-NetTCPConnection -OwningProcess $p.Id -ErrorAction SilentlyContinue |
                Where-Object { $_.RemoteAddress -and $_.RemoteAddress -notin @("0.0.0.0", "::") }
            foreach ($c in $conns) {
                $key = "$($p.ProcessName) -> $($c.RemoteAddress):$($c.RemotePort)"
                if ($seen.ContainsKey($key)) { continue }
                $seen[$key] = $true
                if ($c.RemoteAddress -in @("127.0.0.1", "::1")) {
                    Write-Host ("{0:HH:mm:ss}  ok      {1}" -f (Get-Date), $key)
                } else {
                    $foreign[$key] = $true
                    Write-Host ("{0:HH:mm:ss}  VENKU   {1}" -f (Get-Date), $key) -ForegroundColor Red
                }
            }
        }
        Start-Sleep -Seconds $IntervalSec
    }
} finally {
    Write-Host ""
    if ($foreign.Count -eq 0) {
        Write-Host "Souhrn: žádné spojení mimo 127.0.0.1 ($($seen.Count) místních spojení)." -ForegroundColor Green
    } else {
        Write-Host "Souhrn: $($foreign.Count) spojení mimo tento počítač:" -ForegroundColor Red
        $foreign.Keys | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
    }
}
