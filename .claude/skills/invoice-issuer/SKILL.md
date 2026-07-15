# invoice-issuer 스킬

## 역할
볼타(Bolta) 전자세금계산서 API로 인플루언서 협찬 정산건의 세금계산서를 발행한다.
공급가액에 VAT 10%를 더해 세금계산서(정발행)로 처리한다.

- 문서: https://docs.bolta.io
- Base URL: `https://xapi.bolta.io/v1`
- 인증: HTTP Basic `Authorization: Basic base64(API_KEY:)` + `Supplier-Key` 헤더

## 호출 조건
- 사용자가 계산서 발행을 요청할 때 (`계산서 발행해줘`, `OO 계산서 발행`, `이번 달 계산서 발행`)
- 주문 파이프라인과 **분리된 별도 수동 트리거** (자동 발행 아님)

## 사전 준비 (최초 1회)

### 1. API 키 — `.env`
```
BOLTA_API_KEY_TEST=test_xxxxxxxx
BOLTA_API_KEY_LIVE=live_xxxxxxxx
```
키는 볼타 [개발자센터] → [API 키 생성]에서 발급. 기본은 test, 실발행만 `--live`.

### 2. 공급자(우리 회사) 등록 — `supplier_config.json`
**상태: 초방리마을 사업자등록증 정보 입력 완료** (사업자번호 261-81-27919,
주식회사 초방리마을, 대표 민권식, 평택시 중앙로 151). 남은 항목:
- `manager.email` — 현재 placeholder(`TODO_REPLACE@example.com`). 세금계산서 발급 알림 받을
  우리쪽 담당자 이메일로 교체해야 발행 가능 (가드가 막음).
- `supplierKey` — 비어 있음. 아래 등록 명령으로 발급받아 저장.

API 키 받은 뒤 공급자 등록을 1회 실행해 `supplierKey`를 받아 저장한다:

```powershell
$env:PYTHONUTF8 = "1"
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\invoice-issuer\scripts\issue_invoice.py" `
  --register-supplier
```
출력된 `supplierKey`를 `supplier_config.json`의 `"supplierKey"`에 붙여넣는다.
(test/live의 supplierKey는 호환되지 않으므로 환경별로 따로 등록)

### 3. 공급받는자(인플루언서) — `recipients.json`
유튜버명별 사업자/주민번호·상호·대표자명·담당자 이메일을 채운다.
**담당자 이메일은 볼타 필수 필드** — 없으면 발행이 스킵된다.
사업자등록증(이미지/PDF) 또는 텍스트를 받아 해당 항목을 채워 넣는다.
현재 5명(코앞의경제·바다로간배스·C맹씨·낚시중독·부부초) 주민번호 시드됨, 이메일은 전부 비어 있음.

## ⚡ API 키 받은 직후 실행 순서
1. `.env`에 `BOLTA_API_KEY_TEST` 추가
2. `supplier_config.json`의 `manager.email`을 실제 이메일로 교체
3. 공급자 등록: `--register-supplier` → 출력된 supplierKey를 `supplier_config.json`에 저장
4. dry-run 미리보기로 대상·금액·누락 확인
5. 발행할 인플루언서의 `recipients.json` 이메일 채우기
6. test 발행 → 검증 → (사용자 확인 후) `--live`

> Cloudflare가 기본 python UA를 차단하므로 bolta_client.py는 브라우저 UA를 보낸다 (수정 금지).

## 실행 방법

### 미리보기 (dry-run, 키 없이 가능)
```powershell
& "C:\Users\user\비서\.venv\Scripts\python.exe" `
  "C:\Users\user\비서\.claude\skills\invoice-issuer\scripts\issue_invoice.py" `
  --month 2026-06 --dry-run
```

### 정산DB 자동 발행 (test)
```powershell
& "...python.exe" "...issue_invoice.py" --month 2026-06
```
`site/data/history/2026-06.json`의 인플루언서별 `amount`(공급가액)를 읽어 일괄 발행.
`기타/일반`과 amount=0은 제외.

### 특정 인플루언서만 / 금액 수동
```powershell
& "...issue_invoice.py" --recipient 코앞의경제 --amount 600000
& "...issue_invoice.py" --month 2026-06 --recipient 코앞의경제   # 자동 금액에서 1명만
```

### 라이브 발행
검증 완료 후 `--live` 추가. **실제 국세청 발행**이므로 dry-run으로 먼저 확인.
```powershell
& "...issue_invoice.py" --month 2026-06 --live
```

## 입력
| 인자 | 설명 |
|------|------|
| `--month YYYY-MM` | 정산DB 스냅샷에서 공급가액 자동 추출 |
| `--recipient 이름` | 특정 유튜버명만 |
| `--amount N` | 공급가액 수동 (--recipient와 함께) |
| `--live` | 라이브 발행 (기본 test) |
| `--dry-run` | 발행 없이 payload 미리보기 |
| `--register-supplier` | 공급자 등록 1회 |

## 출력
- 콘솔: 발행 대상별 공급가/세액/합계, issuanceKey 또는 오류
- `output/invoices/{월}_발행로그_{TEST|LIVE}_{타임스탬프}.json` — 발행 결과 로그

## 금액 계산 원칙
- 공급가액 = 정산 `amount` (구간 단가 × 수량, settlement-generator 산출값)
- 세액 = `round(공급가액 × 0.10)`
- 합계 = 공급가액 + 세액
- `purpose: "CLAIM"`(청구), 면세 아님

## 수정발행 (amend_invoice.py)

원본 issuanceKey가 필요하며, `output/invoices/` 발행로그에서 유튜버명(+월)으로 자동 조회한다.

| 유형 | `--type` | 인자 | 의미 |
|------|----------|------|------|
| 공급가액 변동 | `changeSupplyCost` | `--new-amount` 또는 `--diff` | 차액(+/-)만 발행 |
| 계약의 해제 | `termination` | (해제일 자동/`--date`) | 원본 전액 상계 |
| 착오 이중발급 | `doubleIssuance` | 없음 | 원본 상계 (본문 없음) |

```powershell
# 원본 조회만
& "...amend_invoice.py" --recipient 코앞의경제 --find
# 공급가액 600,000 -> 500,000 수정 (test, 미리보기)
& "...amend_invoice.py" --recipient 코앞의경제 --type changeSupplyCost --new-amount 500000 --dry-run
# 계약 해제 / 이중발급 취소
& "...amend_invoice.py" --recipient 코앞의경제 --type termination
& "...amend_invoice.py" --recipient 코앞의경제 --type doubleIssuance
# 라이브 (사용자 확인 후)
& "...amend_invoice.py" --recipient 코앞의경제 --type termination --live
```
- 엔드포인트: `POST /v1/taxInvoices/{issuanceKey}/amend/{type}`
- `changeSupplyCost`는 **차이값**을 전달 (원본 대비 +/- 금액 + VAT)
- 원본을 못 찾으면 `--issuance-key`로 직접 지정
- 로그: `output/invoices/{월}_수정발행_{TEST|LIVE}_{타임스탬프}.json`

## 에러 처리
| 상황 | 처리 |
|------|------|
| recipients.json에 정보 없음 | 해당 건 스킵 + 사업자등록증 요청 |
| 담당자 이메일/식별번호 누락 | 해당 건 스킵 + 누락 항목 보고 |
| supplierKey 미설정 | 중단 — 공급자 등록 안내 |
| 수정발행 원본 못 찾음 | 중단 — issuanceKey 직접 입력 요청 |
| API 4xx/5xx | 발행: 건별 error 기록 후 계속 / 수정발행: 중단 |
| 멱등성 | `Bolta-Client-Reference-Id`로 동일건 중복 발행 방지 |

## 파일 구성
| 파일 | 역할 |
|------|------|
| `scripts/bolta_client.py` | 볼타 API 래퍼 (발행·수정발행·조회) |
| `scripts/issue_invoice.py` | 정발행 스크립트 |
| `scripts/amend_invoice.py` | 수정발행 스크립트 (3종 + 원본 자동조회) |
| `scripts/supplier_config.json` | 공급자(우리) 정보 + supplierKey |
| `scripts/recipients.json` | 공급받는자(인플루언서) 사업자정보 DB |

> 자율 판단(발행 vs 수정발행 유형 제안, 사업자등록증 파싱)은 `invoice-agent` 서브에이전트가 담당.
