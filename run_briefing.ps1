# run_briefing.ps1
# 역할: venv 활성화 후 extract.py 실행 (STEP 1)
# 이후: Claude Code에서 '브리핑 실행해줘' 입력하여 STEP 2~3 진행

$VENV_PYTHON = "C:\Users\user\비서\.venv\Scripts\python.exe"
$SCRIPT     = "C:\Users\user\비서\.claude\skills\excel-parser\scripts\extract.py"
$OUTPUT_DIR = "C:\Users\user\비서\output"
$RESULT_DIR = "C:\Users\user\비서\브리핑결과"

# 출력 폴더 자동 생성
if (-not (Test-Path $OUTPUT_DIR)) { New-Item -ItemType Directory -Path $OUTPUT_DIR -Force | Out-Null }
if (-not (Test-Path $RESULT_DIR)) { New-Item -ItemType Directory -Path $RESULT_DIR -Force | Out-Null }

# venv 존재 확인
if (-not (Test-Path $VENV_PYTHON)) {
    Write-Host "[ERROR] venv가 없습니다. 먼저 다음을 실행하세요:" -ForegroundColor Red
    Write-Host "  python -m venv C:\Users\user\비서\.venv" -ForegroundColor Yellow
    Write-Host "  C:\Users\user\비서\.venv\Scripts\pip install pandas openpyxl" -ForegroundColor Yellow
    exit 1
}

Write-Host "[STEP 1] 엑셀 파싱 시작..." -ForegroundColor Cyan
$env:PYTHONUTF8 = "1"
& $VENV_PYTHON $SCRIPT

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[STEP 1 완료] JSON 생성 성공" -ForegroundColor Green
    Write-Host ""
    Write-Host "다음 단계: Claude Code에서 '브리핑 실행해줘' 를 입력하세요." -ForegroundColor Yellow
} else {
    Write-Host "[ERROR] extract.py 실행 실패 (종료 코드: $LASTEXITCODE)" -ForegroundColor Red
    exit 1
}
