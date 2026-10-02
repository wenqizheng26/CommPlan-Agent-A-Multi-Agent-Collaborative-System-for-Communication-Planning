param([int]$Seconds = 420)
$pids = 27420, 36488, 36052
$out = 'C:\Users\nntm\AppData\Local\Temp\claude\E--codex-------AI\449b053b-aa9c-45d9-9983-b7ba642d9a73\scratchpad\netwatch.csv'
"time,pid,local,remote,state" | Set-Content $out
$end = (Get-Date).AddSeconds($Seconds); $n = 0
while ((Get-Date) -lt $end) {
  $n++
  foreach ($c in Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -in $pids -and $_.State -ne 'Listen' }) {
    "{0},{1},{2}:{3},{4}:{5},{6}" -f (Get-Date -Format HH:mm:ss), $c.OwningProcess, $c.LocalAddress, $c.LocalPort, $c.RemoteAddress, $c.RemotePort, $c.State | Add-Content $out
  }
  foreach ($u in Get-NetUDPEndpoint -ErrorAction SilentlyContinue | Where-Object { $_.OwningProcess -in $pids }) {
    "{0},{1},udp {2}:{3},-,udp" -f (Get-Date -Format HH:mm:ss), $u.OwningProcess, $u.LocalAddress, $u.LocalPort | Add-Content $out
  }
  Start-Sleep -Milliseconds 500
}
"samples,$n" | Add-Content $out
