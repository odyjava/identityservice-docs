# Identity Service — 整合指南（對外）

> 本文件為**自包含**整合規格：任何開發者或 AI 讀完即可建立連線並開發客戶端。
> 對象是「接入平台」（廠商）與其後端／前端。所有範例可直接複製執行。
> 本文不含任何基礎設施機敏資訊；請向服務營運方索取你的 **平台代碼（platform code）** 與 **S2S API Key**。

---

## 1. 服務端點

| 項目 | 值 |
|------|-----|
| API Base URL | `https://identity.lifeintent.app/v1` |
| 健康檢查（根層，無 `/v1`） | `https://identity.lifeintent.app/livez`、`/readyz` |
| 傳輸 | JSON over HTTPS；請求與回應皆 `Content-Type: application/json` |
| 字元集 | UTF-8 |
| 未知欄位 | 一律拒絕（回 422）；請勿送出規格外欄位 |

回應包絡：成功資料一律包在 `{"data": ...}`；錯誤一律包在 `{"error": {...}}`（見 §8）。

---

## 2. 核心概念

- **平台（platform / realm）**：每個接入產品是一個獨立平台，以 **platform code**（如 `topinkiwi`）識別；資料、簽章金鑰、政策完全隔離。你會被指派一個 platform code。
- **租戶（tenant）**：平台**之內**的命名空間（例如商城裡的各商家）。無租戶概念的平台，`tenant` 一律傳空字串 `""`。
- **帳號識別 `sub`**：每個帳號有一個全域唯一、穩定的 `sub`（格式 `acc_` + 26 字），等同 JWT 的 `sub`。你的系統以此鍵連結你自己的業務資料。
- **帳號類型 `type`**：`member`（一般會員）或 `staff`（管理者，access token 效期較短）。

### 平台解析（每個請求都需要）

除健康檢查外，所有 `/v1/*` 請求都必須能解析出所屬平台。請在**每個請求**帶上 header：

```
X-Session-Platform-Code: <你的 platform code>
```

無法解析或未知平台 → `400 AUTH_PLATFORM_UNKNOWN (2013)`，且不會進行後續任何驗證。

---

## 3. 認證方式總覽

| 情境 | 認證 | Header |
|------|------|--------|
| 使用者登入 / 換發 / 登出 / MFA 驗證 / JWKS | 無（走 body 內的帳密或 token） | `X-Session-Platform-Code` |
| MFA 綁定管理（setup/activate/disable） | 使用者 access JWT | `X-Session-Platform-Code` + `Authorization: Bearer <access_token>` |
| S2S 帳號供應（`/internal/*`） | 平台 API Key | `X-Session-Platform-Code` + `Authorization: Bearer <sk_... API Key>` |

- **API Key** 形如 `sk_...`，由服務營運方為你的平台簽發，**只能操作你自己平台**的帳號（跨平台一律 401）。請存入你的密鑰管理系統，切勿寫入原始碼或日誌。

---

## 4. 整合流程（Recipes）

### 4.1 供應帳號（你的後端 → S2S）

在你的會員註冊流程中，由**你的後端**呼叫，建立 authN 帳號並取回 `sub`：

```bash
curl -X POST https://identity.lifeintent.app/v1/internal/accounts \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Authorization: Bearer <sk_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"tenant":"","type":"member","username":"alice","password":"S3cure-Pass!"}'
```

回應 `201`：

```json
{ "data": { "sub": "acc_01KW..." } }
```

- 冪等：同 `(platform, tenant, username)` 重複供應回 `409 COMMON_IDEMPOTENCY_CONFLICT (1004)`；你的編排可視為「已存在」。
- 密碼上限 1024 字；由本服務以 Argon2id 雜湊儲存，你的系統不需也不應保存密碼。
- 取回的 `sub` 請存進你的使用者資料表，作為與本服務的關聯鍵。

### 4.2 使用者登入（你的前端 / 後端）

```bash
curl -X POST https://identity.lifeintent.app/v1/auth/login \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"S3cure-Pass!","tenant":""}'
```

**兩種成功回應（HTTP 皆 200）：**

未啟用 MFA — 直接發 token：
```json
{ "data": { "access_token": "eyJ...", "refresh_token": "rt_...", "expires_in": 2700 } }
```

已啟用 MFA — 回暫態挑戰票，需續走 §4.3：
```json
{ "data": { "mfa_required": true, "mfa_token": "mfa_..." } }
```

**判斷邏輯**：先看 `data.mfa_required` 是否為 `true`；否則取 `data.access_token`。

失敗（見 §8）：`401 (2001)` 帳密錯誤、`403 (2002)` 帳號停用、`423 (2003)` 暫時鎖定。

### 4.3 MFA 第二步（若 login 回 mfa_required）

以 `mfa_token` + 使用者驗證器的 6 位數完成登入：

```bash
curl -X POST https://identity.lifeintent.app/v1/auth/mfa/verify \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Content-Type: application/json" \
  -d '{"mfa_token":"mfa_...","code":"123456"}'
```

回應 `200`：同 TokenResponse。`mfa_token` 效期 5 分鐘、一次性（碼錯需重新 login 取新票）。
手機遺失改用備援碼：`POST /auth/mfa/recovery`，body `{"mfa_token","recovery_code"}`。

### 4.4 換發 access token（session 續期）

access token 到期前，用 refresh token 換一組新的：

```bash
curl -X POST https://identity.lifeintent.app/v1/auth/refresh \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"rt_..."}'
```

回應 `200`：新的 `access_token` + **新的** `refresh_token`（每次換發即輪替，舊 refresh 立即作廢）。

> **安全鐵則**：refresh token 只用一次。若已作廢的 refresh 再度被使用，服務判定為盜用，**立即撤銷該帳號全部 refresh**（回 `401 AUTH_REFRESH_REUSED (2009)`）。你的客戶端務必只保留最新一張、換發成功後立即丟棄舊的。

### 4.5 登出

```bash
curl -X POST https://identity.lifeintent.app/v1/auth/logout \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Content-Type: application/json" \
  -d '{"refresh_token":"rt_..."}'
```

回應一律 `204`（不透露 token 是否存在）。已簽發的短效 access 於自然到期後失效。

### 4.6 在你的後端驗證 access token（本地驗簽）

你的資源伺服器**不需回呼本服務**即可驗證 access JWT——取 JWKS 公鑰本地驗簽：

1. 取公鑰集合：`GET https://identity.lifeintent.app/v1/.well-known/jwks.json`
   （帶 `X-Session-Platform-Code`；回應可快取 5 分鐘，`kid` 對應 JWT header 的 `kid`）
2. 以 JWK 驗證 JWT 簽章（**只接受 `RS256`，拒絕 `alg=none` 或其他**）。
3. 驗證 claims：
   - `iss` 必須等於 `login.<你的 platform code>`
   - `aud` 必須等於你的 platform code
   - `exp` 未過期
   - 依需要讀 `sub`（帳號）、`tenant_id`、`type`

Access token claims 範例：

```json
{
  "iss": "login.topinkiwi",
  "sub": "acc_01KW...",
  "aud": "topinkiwi",
  "tenant_id": "",
  "type": "member",
  "iat": 1751700000,
  "exp": 1751702700,
  "jti": "01KW..."
}
```

效期：`member` 45 分鐘（`expires_in: 2700`）、`staff` 12 分鐘（`720`）。

### 4.7 帳號管理（你的後端 → S2S）

停用／啟用、重設密碼、或緊急撤銷（三選一）：

```bash
curl -X PATCH https://identity.lifeintent.app/v1/internal/accounts/<sub> \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Authorization: Bearer <sk_API_KEY>" \
  -H "Content-Type: application/json" \
  -d '{"status":"disabled"}'          # 或 {"status":"active"}
  #  -d '{"reset_password":"新密碼"}'   # 覆寫密碼並清除鎖定
  #  -d '{"revoke_all":true}'          # 緊急撤銷該帳號全部 refresh（如帳號被盜）
```

回應 `200`：`{ "data": { "sub": "...", "applied": true } }`。帳號不存在回 `404 COMMON_NOT_FOUND (1002)`。
（停用會同時撤銷該帳號全部 refresh。）

---

## 5. 端點速查

| 方法 | 路徑 | 認證 | 用途 |
|------|------|------|------|
| POST | `/auth/login` | 平台 | 帳密登入（回 token 或 MFA 挑戰） |
| POST | `/auth/refresh` | 平台 | 換發（輪替） |
| POST | `/auth/logout` | 平台 | 登出撤銷 refresh |
| GET | `/.well-known/jwks.json` | 平台 | 公開驗章公鑰 |
| POST | `/auth/mfa/verify` | 平台 | MFA 登入第二步（TOTP） |
| POST | `/auth/mfa/recovery` | 平台 | 備援碼登入 |
| POST | `/auth/mfa/setup` | JWT | 開始綁定 MFA（回 QR 用 otpauth URI） |
| POST | `/auth/mfa/activate` | JWT | 驗第一碼啟用，回 10 組備援碼 |
| POST | `/auth/mfa/disable` | JWT | 關閉 MFA（需密碼＋當下 TOTP 碼） |
| POST | `/internal/accounts` | API Key | 供應帳號 |
| PATCH | `/internal/accounts/{sub}` | API Key | 停用／重設密碼／緊急撤銷 |
| GET | `/livez`、`/readyz`（根層） | 無 | 健康檢查 |

### MFA 綁定端點細節（需使用者 access JWT）

- `setup` → `200 { "data": { "secret": "BASE32...", "otpauth_uri": "otpauth://totp/..." } }`（畫 QR 給驗證器掃描；已啟用回 `409 (2006)`）
- `activate`（body `{"code":"123456"}`）→ `200 { "data": { "enabled": true, "recovery_codes": ["XXXXX-XXXXX", ...共 10 組] } }`（備援碼**僅此一次**明碼回傳）
- `disable`（body `{"password","code"}`）→ `200 { "data": { "enabled": false } }`

---

## 6. Token 與憑證規格

| 憑證 | 形式 | 效期 | 規則 |
|------|------|------|------|
| Access Token | JWT，RS256 | member 45m / staff 12m | 本地 JWKS 驗簽；驗 iss/aud/exp |
| Refresh Token | 不透明 `rt_...` | ~30 天滑動 | 每次換發輪替；重用即整帳號撤銷 |
| mfa_token | 不透明 `mfa_...` | 5 分鐘 | 一次性挑戰票 |
| 備援碼 | `XXXXX-XXXXX` | — | 一次性，僅啟用時顯示一次 |
| API Key | `sk_...` | 長期 | per-platform、僅供 S2S、勿外洩 |

---

## 7. 客戶端實作建議

- **前端**：access token 存記憶體（勿放 localStorage）；refresh 走 httpOnly cookie 或記憶體 + 靜默續期。
- **401 處理**：收到 `2010`（access 過期）時自動走 refresh 重試一次；`2009`/`2008` 代表 refresh 失效，導使用者重新登入。
- **時鐘**：MFA 允許 ±30 秒誤差；請確保裝置時間同步。
- **重試**：`5xx`／`429 (1003)` 可指數退避重試；`4xx` 業務錯誤請勿重試。
- **記錄**：切勿記錄 access/refresh token、密碼、API Key、MFA secret、備援碼。
- **trace_id**：每個錯誤回應含 `trace_id`，回報問題時附上可加速排查。

---

## 8. 錯誤格式與錯誤碼

所有錯誤統一格式，`message` 依 `Accept-Language`（`en` / `zh-TW`）在地化：

```json
{ "error": { "code": "AUTH_INVALID_CREDENTIALS", "id": 2001, "message": "帳號或密碼錯誤", "trace_id": "..." } }
```

- 以 **`code`（穩定字串）** 做程式判斷；`id` 供 i18n 對照；`message` 僅供顯示。

| id | code | HTTP | 說明 / 客戶端動作 |
|----|------|------|------|
| 1000 | `COMMON_INTERNAL_ERROR` | 500 | 內部錯誤，憑 trace_id 回報 |
| 1001 | `COMMON_VALIDATION_FAILED` | 422 | 請求格式/欄位錯誤，修正後再送 |
| 1002 | `COMMON_NOT_FOUND` | 404 | 資源不存在 |
| 1003 | `COMMON_RATE_LIMITED` | 429 | 過於頻繁，退避重試 |
| 1004 | `COMMON_IDEMPOTENCY_CONFLICT` | 409 | 資源已存在（帳號重複供應） |
| 1005 | `COMMON_FORBIDDEN` | 403 | 已驗證但權限不足 |
| 2001 | `AUTH_INVALID_CREDENTIALS` | 401 | 帳密錯誤（不區分帳號是否存在） |
| 2002 | `AUTH_ACCOUNT_DISABLED` | 403 | 帳號已停用 |
| 2003 | `AUTH_ACCOUNT_LOCKED` | 423 | 多次失敗暫時鎖定，稍後再試 |
| 2004 | `AUTH_MFA_REQUIRED` | 401 | 需 MFA（流程標示） |
| 2005 | `AUTH_MFA_INVALID_CODE` | 401 | TOTP 碼錯誤／挑戰票無效 |
| 2006 | `AUTH_MFA_ALREADY_ENABLED` | 409 | 已啟用，不可重複 setup |
| 2007 | `AUTH_RECOVERY_CODE_INVALID` | 401 | 備援碼無效或已用 |
| 2008 | `AUTH_REFRESH_INVALID` | 401 | refresh 無效/過期，重新登入 |
| 2009 | `AUTH_REFRESH_REUSED` | 401 | refresh 重用偵測，全部撤銷，重新登入 |
| 2010 | `AUTH_TOKEN_EXPIRED` | 401 | access 過期，走 refresh |
| 2011 | `AUTH_TOKEN_INVALID` | 401 | token／API Key 缺失或無效 |
| 2012 | `AUTH_TOKEN_REVOKED` | 401 | access 已被撤銷，重新登入 |
| 2013 | `AUTH_PLATFORM_UNKNOWN` | 400 | 平台無法解析（檢查 `X-Session-Platform-Code`） |

---

## 9. 快速自我驗證

```bash
# 服務存活（不需任何憑證）
curl https://identity.lifeintent.app/livez        # {"status":"live"}

# 取公鑰（帶你的平台代碼）
curl https://identity.lifeintent.app/v1/.well-known/jwks.json \
  -H "X-Session-Platform-Code: <platform_code>"

# 平台代碼錯誤時的預期回應（確認你有正確帶 header）
curl -X POST https://identity.lifeintent.app/v1/auth/login \
  -H "X-Session-Platform-Code: does-not-exist" \
  -H "Content-Type: application/json" -d '{}'
# → 400 AUTH_PLATFORM_UNKNOWN (2013)
```

---

## 10. 需向營運方索取的資訊

開始整合前，請向 Identity Service 營運方取得：

1. **你的 platform code**（realm slug，如 `topinkiwi`）。
2. **S2S API Key**（`sk_...`，用於 `/internal/*` 帳號供應）。
3. 你的平台的 **Token Profile 參數**（如 access 效期），若有非預設需求。

> 供應帳號、登入、驗簽所需的一切都在本文件內；上述三項為你專屬的接入參數。
