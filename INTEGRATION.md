# Identity Service — 整合指南（對外）

> 本文件為**自包含**整合規格：任何開發者或 AI 讀完即可建立連線並開發客戶端。
> 對象是「接入平台」（廠商）與其後端／前端。所有範例可直接複製執行。
> 本文不含任何基礎設施機敏資訊；請向服務營運方索取你的 **平台代碼（platform code）** 與 **S2S API Key**。
>
> 完整逐端點規格請閱讀 [HTML API 文件](https://odyjava.github.io/identityservice-docs/api.html)，
> 或直接下載 [API.md](https://odyjava.github.io/identityservice-docs/API.md) 交給 AI 代理人與開發工具。

---

## 0. 快速上手：從申請到打通（照做即可）

> 本節是**線性教學**：接入方工程師、或代為整合的 AI 代理人，從上到下照做即可完成第一次成功登入與驗簽。細節與其他情境見 §1 之後的參考章節。

### Step 1 — 申請接入（向服務營運方索取）

開始前，向 Identity Service 營運方索取以下參數（這些**無法自行產生**，必須由營運方指派）：

| 一定要 | 說明 |
|--------|------|
| **platform code**（realm slug） | 你的平台識別，如 `topinkiwi`；出現在 header 與 OIDC 路徑 |

依你選的整合模式，額外索取：

| 模式 | 額外要 |
|------|--------|
| **A. S2S ＋ 平台登入**（你的後端管註冊、你的前後端直接呼叫登入） | **S2S API Key**（`sk_...`） |
| **B. OIDC / OAuth**（第三方 client 走標準授權碼登入，你不碰密碼） | **client_id** ＋ 已登記的 **redirect_uri**（Exact 比對） |

Base URL 固定為 `https://identity.lifeintent.app`（見 §1）。

### Step 2 — 驗證連線（約 30 秒，不需任何憑證）

先確認網路與 platform code 正確，再寫任何程式碼：

```bash
# a) 服務存活
curl https://identity.lifeintent.app/livez
# 預期：{"status":"live"}

# b) 帶你的 platform code 取公鑰
curl https://identity.lifeintent.app/v1/.well-known/jwks.json \
  -H "X-Session-Platform-Code: <platform_code>"
# 預期：200，回一組 JWKS keys

# c) 故意帶錯 platform code，確認 header 真的生效
curl -X POST https://identity.lifeintent.app/v1/auth/login \
  -H "X-Session-Platform-Code: does-not-exist" \
  -H "Content-Type: application/json" -d '{}'
# 預期：400，錯誤 code = AUTH_PLATFORM_UNKNOWN (2013)
```

✅ **通過標準**：(a) 回 `live`、(b) 回 200 JWKS、(c) 回 `2013`。三者都對，代表連線與 platform code 就緒。

### Step 3 — 選整合模式

| 你的情況 | 選 | 打通路徑 |
|----------|-----|----------|
| 自家產品，後端能安全保管 API Key，想最快接上 | **模式 A** | Step 4A |
| 獨立／第三方前端、或需標準 OIDC（id_token、PKCE、跨應用 SSO） | **模式 B** | Step 4B |

兩種模式可並存；不確定就先用 **模式 A** 打通，之後再加 B。

### Step 4A — 打通（模式 A：S2S ＋ 平台登入）

照順序做，每步都有預期輸出：

1. **供應一個測試帳號**（你的後端，帶 API Key）→ 詳見 §4.1
   預期 `201` → 記下回傳的 `data.sub`。
2. **用該帳密登入** → 詳見 §4.2
   預期 `200` → 取得 `data.access_token` 與 `data.refresh_token`。
   （若回 `mfa_required:true`，該帳號已綁 MFA，續走 §4.3。）
3. **本地驗簽剛拿到的 access token** → 詳見 §4.6
   用 §Step 2 的 JWKS 公鑰，驗 `RS256` 簽章與 `iss`／`aud`／`exp`。
4. （可選）**換發** → 詳見 §4.4，確認 refresh 輪替可用。

✅ **打通標準**：能對一個 login 取得的 access token 完成**本地驗簽**並讀出 `sub`。到此你已完整打通認證閉環。

### Step 4B — 打通（模式 B：OIDC / OAuth Authorization Code + PKCE）

完整可複製指令見 §4.8；最小順序如下：

1. **產生 PKCE**：`code_verifier`（高熵隨機）＋ `code_challenge = BASE64URL(SHA256(code_verifier))`，另備隨機 `state`、`nonce`。
2. **Discovery**：`GET /realms/<slug>/.well-known/openid-configuration` → 以回傳的 `authorization_endpoint`／`token_endpoint` 為準。
3. **建立授權交易**：`POST /realms/<slug>/oauth/authorize`（帶 client_id／redirect_uri／PKCE challenge）→ 取得 `transaction`。
4. **帳密登入取碼**：`POST /realms/<slug>/oauth/authorize/login`（帶 transaction＋帳密）→ 取得一次性 `code`（MFA 帳號多一步 `/authorize/mfa`）。
5. **換 token**：`POST /realms/<slug>/oauth/token`（**form-urlencoded**，帶 code＋code_verifier＋redirect_uri＋client_id）→ 取得 `access_token`＋`id_token`。
6. **驗簽**：access token 以該 realm JWKS 驗簽；id_token 驗 `aud == client_id` 且 `nonce` 與 Step 1 一致。

✅ **打通標準**：以 `code` ＋ `code_verifier` 成功換到 `access_token`＋`id_token`，且兩者驗簽通過。

### Step 5 — 常見卡關對照

| 症狀 | 原因與解法 |
|------|-----------|
| `400 AUTH_PLATFORM_UNKNOWN (2013)` | 沒帶或帶錯 `X-Session-Platform-Code`（`/realms/*` OIDC 端點則不需此 header） |
| `422 COMMON_VALIDATION_FAILED (1001)` | 送了規格外欄位或格式錯；未知欄位一律拒絕 |
| `401 AUTH_TOKEN_INVALID (2011)`（S2S） | API Key 缺失／錯誤／用在別的平台 |
| OAuth `token` 端點回錯誤 | 多半是用了 JSON；此端點必須 `application/x-www-form-urlencoded` |
| OAuth 授權被拒 | `redirect_uri` 與登記值需**完全一致**（Exact，連結尾斜線都算）；`code_verifier` 要對應原 `code_challenge` |
| `401 AUTH_REFRESH_REUSED (2009)` | 舊 refresh 被重用；務必只保留最新一張，換發成功即丟棄舊的 |

---

## 1. 服務端點

| 項目 | 值 |
|------|-----|
| API Base URL（`/v1` 家族） | `https://identity.lifeintent.app/v1` |
| OIDC / OAuth Base（realm-scoped） | `https://identity.lifeintent.app/realms/{slug}`（issuer 亦同此值，見 §5） |
| 健康檢查（根層，無 `/v1`） | `https://identity.lifeintent.app/livez`、`/readyz` |
| 傳輸 | JSON over HTTPS；OAuth `token`/`revoke`/`introspect` 端點為 `application/x-www-form-urlencoded`，其餘為 `application/json` |
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
| 使用者登入 / 換發 / 登出 / MFA 驗證 / JWKS / 帳號自助 | 無（走 body 內的帳密或 token） | `X-Session-Platform-Code` |
| MFA 綁定管理（setup/activate/disable/regenerate） | 使用者 access JWT | `X-Session-Platform-Code` + `Authorization: Bearer <access_token>` |
| S2S 帳號供應（`/internal/*`） | 平台 API Key | `X-Session-Platform-Code` + `Authorization: Bearer <sk_... API Key>` |
| OIDC / OAuth（`/realms/{slug}/*`，discovery / authorize / login / token / revoke） | 無（realm slug 已在路徑，PKCE 綁定授權碼） | 不需 `X-Session-Platform-Code` |
| OAuth token 內省（`/realms/{slug}/oauth/introspect`） | resource server 的 API Key | `Authorization: Bearer <sk_... API Key>` |

- **API Key** 形如 `sk_...`，由服務營運方為你的平台簽發，**只能操作你自己平台**的帳號（跨平台一律 401）。請存入你的密鑰管理系統，切勿寫入原始碼或日誌。
- **OIDC / OAuth 端點以 realm slug 定位**（路徑中的 `{slug}` 即你的 platform code），因此不需另帶 `X-Session-Platform-Code`。

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

### 4.8 OIDC / OAuth 2.0 授權碼流程（第三方 client）

第三方應用（如獨立 Web 前端）以標準 **Authorization Code + PKCE（S256）** 登入。此家族端點以 realm slug 定位（路徑內即你的 platform code），**不需** `X-Session-Platform-Code`。Public client **無 secret**，改以 PKCE 綁定授權碼。

> 需向營運方索取：你的 **client_id** 與已登記的 **redirect_uri**（Exact 比對）。

**步驟 0 — 產生 PKCE 參數（客戶端本地）**：`code_verifier` = 高熵隨機字串；`code_challenge` = `BASE64URL(SHA256(code_verifier))`。另各產生一個隨機 `state` 與 `nonce`。

**① Discovery（公開，無需認證）**

```bash
curl https://identity.lifeintent.app/realms/<slug>/.well-known/openid-configuration
```

回應含 `issuer`（= `https://identity.lifeintent.app/realms/<slug>`）、`authorization_endpoint`、`token_endpoint`、`jwks_uri` 等；請以此文件為端點來源。

**② 建立授權交易**

```bash
curl -X POST https://identity.lifeintent.app/realms/<slug>/oauth/authorize \
  -H "Content-Type: application/json" \
  -d '{
    "client_id":"<client_id>",
    "redirect_uri":"https://app.example.com/callback",
    "response_type":"code",
    "scope":"openid",
    "state":"<random_state>",
    "nonce":"<random_nonce>",
    "code_challenge":"<BASE64URL(SHA256(verifier))>",
    "code_challenge_method":"S256"
  }'
```

服務驗證 Exact `redirect_uri` / `state` / `nonce` / PKCE 後，回一張**短效、單次**的授權交易憑證 `transaction`。

**③ 以帳密登入取授權碼（含 MFA 分支）**

```bash
curl -X POST https://identity.lifeintent.app/realms/<slug>/oauth/authorize/login \
  -H "Content-Type: application/json" \
  -d '{"transaction":"<transaction>","username":"alice","password":"S3cure-Pass!"}'
```

- 未啟用 MFA → 回一次性授權碼 `{ "code": "<code>" }`。
- 已啟用 MFA → 回 `{ "mfa_required": true, "mfa_token": "mfa_..." }`，再走一步：

```bash
curl -X POST https://identity.lifeintent.app/realms/<slug>/oauth/authorize/mfa \
  -H "Content-Type: application/json" \
  -d '{"transaction":"<transaction>","mfa_token":"mfa_...","code":"123456"}'
```

回一次性授權碼 `{ "code": "<code>" }`。你的 client 依 `redirect_uri` 導回並帶上 `code` 與原 `state`（務必比對 `state` 一致）。

**④ 以授權碼 ＋ PKCE verifier 換 Token**（form-urlencoded，遵循 OAuth 2.0 標準，回應**不套用** `{data}` 包絡）

```bash
curl -X POST https://identity.lifeintent.app/realms/<slug>/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "code=<code>" \
  -d "code_verifier=<code_verifier>" \
  -d "redirect_uri=https://app.example.com/callback" \
  -d "client_id=<client_id>"
```

回應 `200`：

```json
{ "access_token": "eyJ...", "id_token": "eyJ...", "token_type": "Bearer", "expires_in": 300 }
```

- **access token**：`typ=at+jwt`、RS256、5 分鐘。以該 realm 的 JWKS（`GET /realms/<slug>/.well-known/jwks.json`）本地驗簽。
- **id token**：以你的 `client_id` 為 `aud`；請驗證 `nonce` 與先前送出者一致。
- `code`、`transaction`、`mfa_token` 皆一次性、短效；`code_verifier` 未對應原 `code_challenge` 時換發失敗。

### 4.9 Token 撤銷與內省（OAuth 2.0）

撤銷（RFC 7009；不論 token 是否存在一律回成功，不洩漏狀態）：

```bash
curl -X POST https://identity.lifeintent.app/realms/<slug>/oauth/revoke \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=<access_or_refresh_token>"
```

內省（RFC 7662；供 **resource server** 以 S2S API Key 線上查驗 token 狀態）：

```bash
curl -X POST https://identity.lifeintent.app/realms/<slug>/oauth/introspect \
  -H "Authorization: Bearer <sk_API_KEY>" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=<access_token>"
```

- 有效 token 回 `{ "active": true, "sub": "...", "aud": "...", "exp": ... }` 等聲明。
- 無效／過期／已撤銷一律只回 `{ "active": false }`（不洩漏任何細節）。
- 一般情境優先用本地 JWKS 驗簽（§4.6）；需即時得知撤銷狀態時才用內省。

### 4.10 Email 驗證（自助）

請求驗證信（**generic response**：不論 email 是否存在皆回成功，不可用於探測帳號）：

```bash
curl -X POST https://identity.lifeintent.app/v1/auth/email/verify/request \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","tenant":""}'
```

使用者收信後，以信中一次性 token 確認：

```bash
curl -X POST https://identity.lifeintent.app/v1/auth/email/verify/confirm \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Content-Type: application/json" \
  -d '{"token":"<信中 token>"}'
```

Token 僅存 keyed hash、單次使用、有 TTL；逾期或已用回 `401`。

### 4.11 密碼重設（自助）

請求重設信（同為 generic response）：

```bash
curl -X POST https://identity.lifeintent.app/v1/auth/password/reset/request \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","tenant":""}'
```

以信中 token 設定新密碼：

```bash
curl -X POST https://identity.lifeintent.app/v1/auth/password/reset/confirm \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Content-Type: application/json" \
  -d '{"token":"<信中 token>","new_password":"新的強密碼"}'
```

> 重設成功後，**該帳號全部 refresh token 立即撤銷**，所有既有工作階段須重新登入。

### 4.12 高權限帳號 MFA 復原

管理者類（`staff`）帳號遺失 MFA 時的復原流程；請求端點同為 generic response，全程留稽核。兩條完成路徑：

```bash
# 發起復原請求（generic response）
curl -X POST https://identity.lifeintent.app/v1/auth/privileged-recovery/request \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","tenant":""}'

# 路徑一：以備援碼自助完成
curl -X POST https://identity.lifeintent.app/v1/auth/privileged-recovery/complete \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","tenant":"","recovery_code":"XXXXX-XXXXX"}'

# 路徑二：經營運方人工核准後完成
curl -X POST https://identity.lifeintent.app/v1/auth/privileged-recovery/complete-with-approval \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","tenant":"","approval_token":"<核准後取得的一次性憑證>"}'
```

> 上述請求欄位為代表性示意；確切欄位以凍結的 OpenAPI 契約為準。復原完成後建議立即重新綁定 MFA。

### 4.13 重新產生 MFA 備援碼（需使用者 access JWT）

備援碼快用完或疑似外洩時，重新產生一組全新備援碼（**舊碼全部作廢**）。此敏感操作需再次驗證身分（密碼＋當下動態碼）：

```bash
curl -X POST https://identity.lifeintent.app/v1/auth/mfa/recovery-codes/regenerate \
  -H "X-Session-Platform-Code: <platform_code>" \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"password":"S3cure-Pass!","code":"123456"}'
```

回應 `200`：`{ "data": { "recovery_codes": ["XXXXX-XXXXX", ...共 10 組] } }`（**僅此一次**明碼回傳，請立即交付使用者收好）。

---

## 5. 端點速查

**OIDC / OAuth 2.0（realm-scoped，路徑前綴 `/realms/{slug}`）**

| 方法 | 路徑 | 認證 | 用途 |
|------|------|------|------|
| GET | `/.well-known/openid-configuration` | 無 | OIDC Discovery 文件 |
| GET | `/.well-known/jwks.json` | 無 | 該 realm 驗章公鑰 |
| POST | `/oauth/authorize` | 無 | 建立單次授權交易（驗 redirect/state/nonce/PKCE） |
| POST | `/oauth/authorize/login` | 無 | 帳密登入取授權碼（或回 MFA 挑戰） |
| POST | `/oauth/authorize/mfa` | 無 | MFA 第二步後取授權碼 |
| POST | `/oauth/token` | 無（PKCE） | 以 code + verifier 換 access／id token（form） |
| POST | `/oauth/revoke` | 無 | Token 撤銷（RFC 7009，form） |
| POST | `/oauth/introspect` | API Key | Token 內省（RFC 7662，form） |

**`/v1` 家族（路徑前綴 `/v1`；「平台」= 帶 `X-Session-Platform-Code`）**

| 方法 | 路徑 | 認證 | 用途 |
|------|------|------|------|
| POST | `/auth/login` | 平台 | 帳密登入（回 token 或 MFA 挑戰） |
| POST | `/auth/refresh` | 平台 | 換發（輪替） |
| POST | `/auth/logout` | 平台 | 登出撤銷 refresh |
| GET | `/.well-known/jwks.json` | 平台 | 公開驗章公鑰 |
| POST | `/auth/mfa/verify` | 平台 | MFA 登入第二步（TOTP） |
| POST | `/auth/mfa/recovery` | 平台 | 備援碼登入 |
| POST | `/auth/email/verify/request` | 平台 | 請求 email 驗證信（generic） |
| POST | `/auth/email/verify/confirm` | 平台 | 以 token 確認 email |
| POST | `/auth/password/reset/request` | 平台 | 請求密碼重設信（generic） |
| POST | `/auth/password/reset/confirm` | 平台 | 以 token 重設密碼（撤銷全部 refresh） |
| POST | `/auth/privileged-recovery/request` | 平台 | 高權限帳號 MFA 復原請求（generic） |
| POST | `/auth/privileged-recovery/complete` | 平台 | 以備援碼完成復原 |
| POST | `/auth/privileged-recovery/complete-with-approval` | 平台 | 經人工核准後完成復原 |
| POST | `/auth/mfa/setup` | JWT | 開始綁定 MFA（回 QR 用 otpauth URI） |
| POST | `/auth/mfa/activate` | JWT | 驗第一碼啟用，回 10 組備援碼 |
| POST | `/auth/mfa/disable` | JWT | 關閉 MFA（需密碼＋當下 TOTP 碼） |
| POST | `/auth/mfa/recovery-codes/regenerate` | JWT | 重新產生備援碼（需密碼＋TOTP 碼） |
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
| Access Token（`/v1` login） | JWT，RS256 | member 45m / staff 12m | 本地 JWKS 驗簽；驗 iss/aud/exp |
| OAuth Access Token（`/oauth/token`） | JWT，RS256，`typ=at+jwt` | 5 分鐘 | 以 realm JWKS 驗簽；issuer = realm issuer |
| OAuth ID Token | JWT，RS256 | 隨授權 | `aud` = client_id；驗 `nonce` |
| Authorization Code | 不透明 `code` | 短效 | 一次性；換 token 需 PKCE verifier |
| transaction / mfa_token | 不透明 | 短效（mfa_token 5 分鐘） | 一次性授權交易 / 挑戰票 |
| Refresh Token | 不透明 `rt_...` | ~30 天滑動 | 每次換發輪替；重用即整帳號撤銷 |
| 備援碼 | `XXXXX-XXXXX` | — | 一次性，僅啟用／重產時顯示一次 |
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
