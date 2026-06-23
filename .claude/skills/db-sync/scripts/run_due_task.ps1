# Windows scheduled-task wrapper: guarantees file sync (no kakao).
# Shares sync_state.json with the /loop session, so no double-run.
$env:PYTHONUTF8 = "1"
$py  = "C:\Users\user\비서\.venv\Scripts\python.exe"
$scr = "C:\Users\user\비서\.claude\skills\db-sync\scripts\run_due.py"
$log = "C:\Users\user\비서\output\sync_task.log"
$ts  = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $log -Value "===== [$ts] task run =====" -Encoding utf8
& $py $scr *>> $log
Add-Content -Path $log -Value "" -Encoding utf8
