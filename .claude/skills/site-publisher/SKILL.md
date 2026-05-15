# site-publisher 스킬

## 역할
`site/data/` 디렉토리의 JSON 파일을 git으로 커밋·푸시하여 GitHub Pages를 갱신한다.

## 호출 조건
STEP 7 (스냅샷 저장) 완료 후

## 실행 방법

```powershell
$env:PYTHONUTF8 = "1"
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\site-publisher\scripts\publish.py" `
  "2026-05"
```

## 사전 조건
1. `C:\Users\user\비서`가 git 리포지토리여야 함 (`git init` 및 GitHub remote 설정 필요)
2. `git push`가 인증 없이 실행될 수 있어야 함 (SSH key 또는 credential manager 설정)
3. GitHub Pages가 `main` 브랜치의 `/site` 폴더를 소스로 설정되어 있어야 함

## git 설정 방법 (최초 1회)

```powershell
cd C:\Users\user\비서
git init
git remote add origin https://github.com/{USERNAME}/{REPO}.git
git branch -M main
git push -u origin main
```

## 실패 처리
1회 자동 재시도 → 실패 시 로컬 저장만 유지하고 파이프라인 계속 진행.
다음 주문 처리 시 재시도.

## 캐시 무효화
`app.js`에서 `fetch('dashboard.json?v=' + Date.now())`로 항상 최신 데이터를 가져옴.
