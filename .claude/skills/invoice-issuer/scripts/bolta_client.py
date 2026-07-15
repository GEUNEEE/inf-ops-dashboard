# -*- coding: utf-8 -*-
"""
볼타(Bolta) 전자세금계산서 API 래퍼.

문서: https://docs.bolta.io
- Base URL : https://xapi.bolta.io/v1
- 인증     : HTTP Basic  ->  Authorization: Basic base64(API_KEY + ":")
- 공급자키 : Supplier-Key 헤더 (공급자 등록 시 발급)

환경변수 (.env):
  BOLTA_API_KEY_TEST   test_ 로 시작하는 테스트 키
  BOLTA_API_KEY_LIVE   live_ 로 시작하는 라이브 키

live 환경은 호출 측에서 use_live=True 로 명시할 때만 사용한다 (기본 test).
"""
import base64
import json
import os
import urllib.error
import urllib.request

BASE_URL = "https://xapi.bolta.io/v1"


class BoltaError(Exception):
    """볼타 API가 4xx/5xx 또는 코드 본문 오류를 반환했을 때."""

    def __init__(self, status, code, message, raw=None):
        self.status = status
        self.code = code
        self.message = message
        self.raw = raw
        super().__init__(f"[{status}] {code}: {message}")


class BoltaClient:
    def __init__(self, api_key, supplier_key=None, timeout=30):
        if not api_key:
            raise ValueError("볼타 API 키가 비어 있습니다. .env의 BOLTA_API_KEY_* 확인.")
        self.api_key = api_key
        self.supplier_key = supplier_key
        self.timeout = timeout
        self.is_live = api_key.startswith("live_")

    # ── 내부 ──────────────────────────────────────────────
    def _auth_header(self):
        token = base64.b64encode(f"{self.api_key}:".encode("utf-8")).decode("ascii")
        return f"Basic {token}"

    def _request(self, method, path, body=None, extra_headers=None):
        url = f"{BASE_URL}{path}"
        headers = {
            "Authorization": self._auth_header(),
            "Content-Type": "application/json",
            "Accept": "application/json",
            # 볼타 앞단 Cloudflare가 기본 python-urllib UA를 봇으로 차단(Error 1010)하므로
            # 일반 브라우저 UA를 명시한다.
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0.0.0 Safari/537.36"),
        }
        if extra_headers:
            headers.update(extra_headers)

        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                text = resp.read().decode("utf-8")
                return json.loads(text) if text else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="replace")
            code, message = "HTTP_ERROR", raw
            try:
                parsed = json.loads(raw)
                code = parsed.get("code", code)
                message = parsed.get("message", raw)
            except (ValueError, AttributeError):
                pass
            if not (message or "").strip():
                # 본문 없는 상태코드(예: 401)에 사람이 읽을 안내 부여
                hint = {
                    401: "인증 실패 — API 키가 잘못되었거나 만료되었습니다 (.env 확인).",
                    403: "접근 거부 — 키 권한 또는 환경(test/live) 불일치.",
                    404: "엔드포인트를 찾을 수 없음.",
                }.get(e.code, f"HTTP {e.code} 오류 (응답 본문 없음).")
                message = hint
            raise BoltaError(e.code, code, message, raw) from None
        except urllib.error.URLError as e:
            raise BoltaError(0, "NETWORK_ERROR", str(e.reason)) from None

    # ── 공급자(발행자) ────────────────────────────────────
    def register_supplier(self, identification_number, organization_name,
                          representative_name, tax_registration_id=None):
        """공급자 등록. 최초 1회. 반환된 supplierKey를 보관해 재사용한다."""
        body = {
            "identificationNumber": identification_number,
            "organizationName": organization_name,
            "representativeName": representative_name,
        }
        if tax_registration_id:
            body["taxRegistrationId"] = tax_registration_id
        return self._request("POST", "/suppliers", body)

    # ── 세금계산서 정발행 ─────────────────────────────────
    def issue_tax_invoice(self, payload, supplier_key=None, reference_id=None):
        """
        전자세금계산서 정발행.
        payload: 문서 명세대로 구성된 dict (date/purpose/supplier/supplied/items/...).
        반환: {"issuanceKey": "..."}
        """
        sk = supplier_key or self.supplier_key
        if not sk:
            raise ValueError("Supplier-Key가 필요합니다. 공급자 등록 후 supplier_key 설정.")
        extra = {"Supplier-Key": sk}
        if reference_id:
            extra["Bolta-Client-Reference-Id"] = reference_id
        return self._request("POST", "/taxInvoices/issue", payload, extra)

    # ── 세금계산서 조회 ───────────────────────────────────
    def get_tax_invoice(self, issuance_key):
        """발행 완료된 세금계산서 내용 조회. ntsTransactionId(국세청승인번호) 포함."""
        return self._request("GET", f"/taxInvoices/{issuance_key}")

    # ── 수정발행 ──────────────────────────────────────────
    def _amend(self, issuance_key, kind, body, supplier_key=None,
               reference_id=None):
        sk = supplier_key or self.supplier_key
        if not sk:
            raise ValueError("Supplier-Key가 필요합니다.")
        extra = {"Supplier-Key": sk}
        if reference_id:
            extra["Bolta-Client-Reference-Id"] = reference_id
        return self._request(
            "POST", f"/taxInvoices/{issuance_key}/amend/{kind}", body, extra)

    def amend_change_supply_cost(self, issuance_key, date, items,
                                 supplier_key=None, reference_id=None):
        """공급가액 변동 수정발행. items에는 '차이값'(+/-)을 전달."""
        body = {"date": date, "items": items}
        return self._amend(issuance_key, "changeSupplyCost", body,
                           supplier_key, reference_id)

    def amend_termination(self, issuance_key, date, supplier_key=None,
                          reference_id=None):
        """계약의 해제 수정발행. 원본 전액 상계."""
        return self._amend(issuance_key, "termination", {"date": date},
                          supplier_key, reference_id)

    def amend_double_issuance(self, issuance_key, supplier_key=None,
                              reference_id=None):
        """착오에 의한 이중발급 취소. 요청 본문 없음. 작성일자는 원본 자동 적용."""
        return self._amend(issuance_key, "doubleIssuance", None,
                          supplier_key, reference_id)


def load_client(use_live=False, supplier_key=None, env_path=None):
    """.env에서 키를 읽어 BoltaClient를 만든다. 기본 test."""
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path or os.path.join(_project_root(), ".env"))
    except ImportError:
        pass

    key_name = "BOLTA_API_KEY_LIVE" if use_live else "BOLTA_API_KEY_TEST"
    api_key = os.environ.get(key_name, "").strip()
    if not api_key:
        raise ValueError(f".env에 {key_name}가 없습니다.")
    return BoltaClient(api_key, supplier_key=supplier_key)


def _project_root():
    # .../비서/.claude/skills/invoice-issuer/scripts/bolta_client.py → 비서
    here = os.path.abspath(__file__)
    return os.path.abspath(os.path.join(here, "..", "..", "..", "..", ".."))
