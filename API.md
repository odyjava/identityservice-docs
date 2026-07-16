# Identity Service 公開 API 文件

> Base URL：`https://identity.lifeintent.app`
> 文件更新：2026-07-16（Asia/Taipei）
> 適用對象：接入平台的前端、後端、Resource Server 與 AI 開發代理人。
> 公開範圍不包含營運者專用 `/v1/admin/*` 與系統 Webhook `/webhooks/*`。

## 1. 共通規範

Identity Service 提供兩組 API：

- `/realms/{slug}/*`：標準 OIDC/OAuth 2.0，Realm 已包含在 URL，不使用 `X-Session-Platform-Code`。
- `/v1/*`：平台登入、帳號自助、MFA 與 S2S 帳號供應，每次請求必須帶 `X-Session-Platform-Code`。

| 項目 | 規範 |
|---|---|
| TLS | 全部端點只使用 HTTPS |
| JSON | UTF-8；一般有 Payload 的端點使用 `application/json` |
| OAuth Form | `/oauth/token`、`/oauth/revoke`、`/oauth/introspect` 使用 `application/x-www-form-urlencoded` |
| 未知 JSON 欄位 | 拒絕並回驗證錯誤 |
| Request Body 上限 | 64 KiB |
| 時間 | JWT 時間欄位使用 Unix timestamp（秒） |
| 管理 API | `/v1/admin/*` 不屬於公開串接範圍 |

## 2. Headers

| Header | 適用範圍 | 必要性 | 格式與限制 |
|---|---|---|---|
| `Content-Type` | 有 Payload 的請求 | 必要 | 一般 API：`application/json`；OAuth form 端點：`application/x-www-form-urlencoded` |
| `Accept` | 全部 | 選用 | 建議 `application/json` |
| `Accept-Language` | `/v1/*` | 選用 | `zh-TW` 或 `en`；其他值以英文回退 |
| `X-Session-Platform-Code` | `/v1/*` | 必要 | 營運方核發的 platform code／realm slug，例如 `topinkiwi` |
| `Authorization` | Bearer JWT、S2S API Key | 依端點 | `Bearer <access_token>` 或 `Bearer <sk_API_KEY>` |
| `X-Request-Id` | 全部 | 選用 | 1–128 字元，只接受英數字、`.`、`_`、`-`；合法值會在 Response Header 回傳 |

注意：

- `/realms/{slug}/*` 不需要 `X-Session-Platform-Code`。
- `/v1/*` 即使沒有認證，也必須帶 `X-Session-Platform-Code`。
- S2S API Key 只能放在後端 Secret 管理系統，不得放入瀏覽器、Mobile App、原始碼或 Log。
- 錯誤 Response 的 `trace_id` 對應 `X-Request-Id`，回報問題時請一併提供。

## 3. Response 與錯誤格式

### 3.1 `/v1` 成功格式

除 `204 No Content` 外，成功資料包在 `data`：

```json
{
  "data": {
    "example": true
  }
}
```

### 3.2 `/v1` 錯誤格式

```json
{
  "error": {
    "code": "COMMON_VALIDATION_FAILED",
    "id": 1001,
    "message": "請求格式或欄位無效",
    "trace_id": "5b5aa30b-00fd-46ab-a836-322c779ff2c8"
  }
}
```

程式判斷使用穩定字串 `code`；`message` 只供顯示。`429 COMMON_RATE_LIMITED` 會附 `Retry-After` Response Header，客戶端應依秒數等待並採指數退避。

### 3.3 OAuth 錯誤格式

`/realms/{slug}/oauth/*` 遵循 OAuth JSON 錯誤，不使用 `/v1` envelope：

```json
{
  "error": "invalid_grant",
  "error_description": "the authorization grant is invalid"
}
```

OAuth Token 與敏感資料回應帶 `Cache-Control: no-store`、`Pragma: no-cache`。

## 4. OIDC Discovery 與 JWKS

### GET /realms/{slug}/.well-known/openid-configuration

取得 Realm 的 OIDC metadata。

**Headers：** `Accept: application/json`（選用）
**Path Parameters：** `slug`，營運方核發的 Realm slug。
**Query Parameters：** 無。
**Payload：** 無。
**認證：** 無。

```bash
curl https://identity.lifeintent.app/realms/topinkiwi/.well-known/openid-configuration
```

**Success：`200 OK`**

```json
{
  "issuer": "https://identity.lifeintent.app/realms/topinkiwi",
  "jwks_uri": "https://identity.lifeintent.app/realms/topinkiwi/.well-known/jwks.json",
  "authorization_endpoint": "https://identity.lifeintent.app/realms/topinkiwi/oauth/authorize",
  "token_endpoint": "https://identity.lifeintent.app/realms/topinkiwi/oauth/token",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "code_challenge_methods_supported": ["S256"],
  "id_token_signing_alg_values_supported": ["RS256"],
  "subject_types_supported": ["public"]
}
```

**Errors：** Realm 不存在、停權或 slug 格式非法均回相同 `404 COMMON_NOT_FOUND`，避免洩漏 Realm 狀態。
**Security：** 以回傳的 endpoint 為準，不要自行拼接或改成 `/v1/realms/*`。

### GET /realms/{slug}/.well-known/jwks.json

取得該 Realm 的 RS256 公開驗章金鑰。

**Headers：** `Accept: application/json`（選用）
**Path Parameters：** `slug`。
**Query Parameters：** 無。
**Payload：** 無。
**認證：** 無。

**Success：`200 OK`，`Cache-Control: public, max-age=300`**

```json
{
  "keys": [
    {
      "kid": "key-id",
      "kty": "RSA",
      "alg": "RS256",
      "use": "sig",
      "n": "base64url-modulus",
      "e": "AQAB"
    }
  ]
}
```

**Errors：** 與 Discovery 相同。
**Security：** JWKS 只含公開材料；驗章時依 JWT header 的 `kid` 選鑰，且只接受 `RS256`。

## 5. OAuth 2.0 Authorization Code + PKCE

所有端點使用 `/realms/{slug}`，不帶 `X-Session-Platform-Code`。Public client 無 Client Secret，必須使用 PKCE `S256`。

### POST /realms/{slug}/oauth/authorize

建立短效、一次性的授權交易。

**Headers**

| 名稱 | 必要 | 值 |
|---|---|---|
| `Content-Type` | 是 | `application/json` |

**Path Parameters：** `slug`。
**Query Parameters：** 無。

**Payload**

| 欄位 | 型別 | 必要 | 限制 |
|---|---|---|---|
| `response_type` | string | 是 | 固定 `code` |
| `client_id` | string | 是 | 營運方登記的 client ID |
| `redirect_uri` | string | 是 | 必須與登記值 Exact Match |
| `scope` | string | 是 | 空白分隔；需包含允許的 scope |
| `state` | string | 是 | Client 產生的高熵隨機值 |
| `nonce` | string | 是 | Client 產生，之後驗證 ID Token |
| `code_challenge` | string | 是 | `BASE64URL(SHA256(code_verifier))` |
| `code_challenge_method` | string | 是 | 固定 `S256` |

```json
{
  "response_type": "code",
  "client_id": "topinkiwi-web",
  "redirect_uri": "https://app.example.com/callback",
  "scope": "openid profile",
  "state": "random-state",
  "nonce": "random-nonce",
  "code_challenge": "base64url-sha256",
  "code_challenge_method": "S256"
}
```

**Success：`200 OK`**

```json
{
  "transaction": "txn_opaque_value",
  "expires_in": 300
}
```

**Errors：** `invalid_request`、`unauthorized_client`、`invalid_scope`；Realm 不存在或停權為不可區分的 `404 invalid_request`。
**Security：** `state`、`nonce`、`code_verifier` 必須由 CSPRNG 產生；不得記錄密碼或交易 handle。

### POST /realms/{slug}/oauth/authorize/login

以帳密完成授權交易；若帳號已啟用 MFA，先回 MFA challenge。

**Headers：** `Content-Type: application/json`
**Path Parameters：** `slug`。
**Query Parameters：** 無。

**Payload**

| 欄位 | 型別 | 必要 | 說明 |
|---|---|---|---|
| `transaction` | string | 是 | authorize 回傳的一次性交易 handle |
| `tenant` | string | 是 | 無租戶時傳空字串 |
| `username` | string | 是 | 使用者帳號 |
| `password` | string | 是 | 使用者密碼 |

```json
{
  "transaction": "txn_opaque_value",
  "tenant": "",
  "username": "alice",
  "password": "S3cure-Pass!"
}
```

**Success A：`200 OK`，無 MFA**

```json
{
  "code": "authorization-code",
  "state": "random-state",
  "redirect_uri": "https://app.example.com/callback"
}
```

**Success B：`200 OK`，需要 MFA**

```json
{
  "mfa_required": true,
  "mfa_token": "mfa_opaque_value"
}
```

**Errors：** `invalid_grant`、`access_denied`、`invalid_transaction`。
**Security：** Client 收到結果後必須比對 `state`，授權碼短效且一次性。

### POST /realms/{slug}/oauth/authorize/mfa

以 MFA challenge 與 TOTP 完成授權交易。

**Headers：** `Content-Type: application/json`
**Path Parameters：** `slug`。
**Query Parameters：** 無。

**Payload**

```json
{
  "transaction": "txn_opaque_value",
  "mfa_token": "mfa_opaque_value",
  "code": "123456"
}
```

三個欄位皆為必要 string；`code` 為驗證器當下的 6 位數。

**Success：`200 OK`**

```json
{
  "code": "authorization-code",
  "state": "random-state",
  "redirect_uri": "https://app.example.com/callback"
}
```

**Errors：** `invalid_grant`、`invalid_transaction`、`access_denied`。
**Security：** `transaction`、`mfa_token` 與 TOTP challenge 均短效且一次性。

### POST /realms/{slug}/oauth/token

以 Authorization Code + PKCE 或 Refresh Token 取得 Token。

**Headers：** `Content-Type: application/x-www-form-urlencoded`
**Path Parameters：** `slug`。
**Query Parameters：** 無。
**認證：** Public client 不使用 Client Secret。

**Authorization Code Payload**

| 欄位 | 必要 | 值 |
|---|---|---|
| `grant_type` | 是 | `authorization_code` |
| `code` | 是 | 上一步取得的一次性授權碼 |
| `redirect_uri` | 是 | 必須與 authorize 時完全相同 |
| `client_id` | 是 | 登記的 client ID |
| `code_verifier` | 是 | 對應原 `code_challenge` 的 PKCE verifier |

```bash
curl -X POST https://identity.lifeintent.app/realms/topinkiwi/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "code=authorization-code" \
  -d "redirect_uri=https://app.example.com/callback" \
  -d "client_id=topinkiwi-web" \
  -d "code_verifier=original-verifier"
```

**Success：`200 OK`**

```json
{
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "expires_in": 300,
  "id_token": "eyJ...",
  "scope": "openid profile",
  "refresh_token": "ort_selector.secret"
}
```

**Refresh Token Payload**

| 欄位 | 必要 | 值 |
|---|---|---|
| `grant_type` | 是 | `refresh_token` |
| `refresh_token` | 是 | 最近一次取得的 OAuth Refresh Token |
| `client_id` | 是 | 原 client ID |

Refresh 成功回新的 `access_token`、`refresh_token`、`token_type`、`expires_in`、`scope`，不回新的 `id_token`。

**Errors：** `invalid_request`、`invalid_client`、`invalid_grant`、`unsupported_grant_type`。
**Security：** Refresh Token 每次使用後輪替；只能保留最新一張。Authorization Code 驗證失敗後不得重用。

### POST /realms/{slug}/oauth/revoke

撤銷 Access 或 Refresh Token，遵循 RFC 7009。

**Headers：** `Content-Type: application/x-www-form-urlencoded`
**Path Parameters：** `slug`。
**Query Parameters：** 無。

**Payload**

| 欄位 | 必要 | 說明 |
|---|---|---|
| `token` | 是 | 要撤銷的 Token |
| `client_id` | 是 | Token 所屬 client |

**Success：`200 OK`**

```json
{}
```

Token 是否存在皆回相同成功結果。
**Errors：** Client 不存在或停權回 `401 invalid_client`；格式錯誤回 `invalid_request`。
**Security：** 不得依 Response 推斷 Token 是否曾存在。

### POST /realms/{slug}/oauth/introspect

Resource Server 以 S2S API Key 查詢 Token 狀態，遵循 RFC 7662。

**Headers**

| 名稱 | 必要 | 值 |
|---|---|---|
| `Authorization` | 是 | `Bearer <sk_API_KEY>` |
| `Content-Type` | 是 | `application/x-www-form-urlencoded` |

**Path Parameters：** `slug`。
**Query Parameters：** 無。
**Payload：** `token=<access_or_refresh_token>`。

**Inactive：`200 OK`**

```json
{"active": false}
```

**Active：`200 OK`**

```json
{
  "active": true,
  "scope": "openid profile",
  "client_id": "topinkiwi-web",
  "sub": "acc_01...",
  "exp": 1780000000,
  "iat": 1779999700,
  "sid": "ses_01...",
  "token_type": "access_token",
  "iss": "https://identity.lifeintent.app/realms/topinkiwi"
}
```

**Errors：** 缺少、錯誤或跨 Realm API Key 一律回相同 `401 invalid_client`。
**Security：** 一般請求優先本地 JWKS 驗章；只有需要即時撤銷狀態時使用 Introspection。

## 6. 登入與 Session

本章所有 `/v1/*` 端點都要帶 `X-Session-Platform-Code`。

### POST /v1/auth/login

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Path Parameters：** 無。
**Query Parameters：** 無。

**Payload**

| 欄位 | 型別 | 必要 | 說明 |
|---|---|---|---|
| `username` | string | 是 | 帳號 |
| `password` | string | 是 | 密碼 |
| `tenant` | string | 是 | 無租戶時傳 `""` |

```json
{"username":"alice","password":"S3cure-Pass!","tenant":""}
```

**Success A：`200 OK`**

```json
{"data":{"access_token":"eyJ...","refresh_token":"rt_...","expires_in":2700}}
```

**Success B：`200 OK`**

```json
{"data":{"mfa_required":true,"mfa_token":"mfa_..."}}
```

**Errors：** `AUTH_INVALID_CREDENTIALS`、`AUTH_ACCOUNT_DISABLED`、`AUTH_ACCOUNT_LOCKED`、`COMMON_VALIDATION_FAILED`、`AUTH_PLATFORM_UNKNOWN`、`COMMON_RATE_LIMITED`。
**Security：** Response 帶 `Cache-Control: no-store`；帳號不存在與密碼錯誤不可區分。

### POST /v1/auth/refresh

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Path／Query Parameters：** 無。

**Payload**

```json
{"refresh_token":"rt_..."}
```

**Success：`200 OK`**

```json
{"data":{"access_token":"eyJ...","refresh_token":"rt_new...","expires_in":2700}}
```

**Errors：** `AUTH_REFRESH_INVALID`、`AUTH_REFRESH_REUSED`、`COMMON_VALIDATION_FAILED`。
**Security：** Refresh Token 每次換發立即輪替；重用舊 Token 會撤銷該帳號所有 Refresh Token。

### POST /v1/auth/logout

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Path／Query Parameters：** 無。
**Payload：** `{"refresh_token":"rt_..."}`。
**Success：`204 No Content`，無 Response body。
**Errors：** Payload 無效時為 `COMMON_VALIDATION_FAILED`。
**Security：** 有效或不存在的 Token 不應造成可辨識差異。

### GET /v1/.well-known/jwks.json

取得 platform profile 的公開驗章金鑰。

**Headers：** `X-Session-Platform-Code`
**Path／Query Parameters：** 無。
**Payload：** 無。
**Success：** `200 OK`，格式同 Realm JWKS，`Cache-Control: public, max-age=300`。
**Errors：** `AUTH_PLATFORM_UNKNOWN`、`COMMON_INTERNAL_ERROR`。
**Security：** `/v1` Access Token 驗證需同時檢核 RS256 簽章、`iss`、`aud`、`exp` 與允許的 `typ`。

## 7. MFA

### POST /v1/auth/mfa/verify

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"mfa_token":"mfa_...","code":"123456"}`。
**Path／Query Parameters：** 無。
**Success：** `200 OK`，回 TokenResponse。
**Errors：** `AUTH_MFA_INVALID_CODE`、`COMMON_VALIDATION_FAILED`。
**Security：** `mfa_token` 5 分鐘、一次性；驗證失敗也會消耗。

### POST /v1/auth/mfa/recovery

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"mfa_token":"mfa_...","recovery_code":"XXXXX-XXXXX"}`。
**Path／Query Parameters：** 無。
**Success：** `200 OK`，回 TokenResponse。
**Errors：** `AUTH_RECOVERY_CODE_INVALID`、`AUTH_MFA_INVALID_CODE`、`COMMON_VALIDATION_FAILED`。
**Security：** 備援碼使用後立即失效。

### POST /v1/auth/mfa/setup

**Headers：** `X-Session-Platform-Code`、`Authorization: Bearer <access_token>`
**Content-Type／Payload：** 無。
**Path／Query Parameters：** 無。

**Success：`200 OK`**

```json
{"data":{"secret":"BASE32SECRET","otpauth_uri":"otpauth://totp/..."}}
```

**Errors：** `AUTH_TOKEN_INVALID`、`AUTH_TOKEN_EXPIRED`、`AUTH_TOKEN_REVOKED`、`AUTH_MFA_ALREADY_ENABLED`。
**Security：** `secret` 只用於當次綁定畫面，不得寫入 Log。

### POST /v1/auth/mfa/activate

**Headers：** `X-Session-Platform-Code`、`Authorization: Bearer <access_token>`、`Content-Type: application/json`
**Payload：** `{"code":"123456"}`。
**Path／Query Parameters：** 無。

**Success：`200 OK`**

```json
{"data":{"enabled":true,"recovery_codes":["XXXXX-XXXXX","...共 10 組"]}}
```

**Errors：** `AUTH_MFA_INVALID_CODE`、`AUTH_TOKEN_INVALID`、`COMMON_VALIDATION_FAILED`。
**Security：** Recovery Codes 僅此一次明文回傳，Client 必須立即交付使用者安全保存。

### POST /v1/auth/mfa/disable

**Headers：** `X-Session-Platform-Code`、`Authorization: Bearer <access_token>`、`Content-Type: application/json`
**Payload：** `{"password":"current-password","code":"123456"}`。
**Path／Query Parameters：** 無。
**Success：** `200 OK`，`{"data":{"enabled":false}}`。
**Errors：** `AUTH_INVALID_CREDENTIALS`、`AUTH_MFA_INVALID_CODE`、`AUTH_TOKEN_INVALID`。
**Security：** 停用會使既有 Recovery Codes 作廢。

### POST /v1/auth/mfa/recovery-codes/regenerate

**Headers：** `X-Session-Platform-Code`、`Authorization: Bearer <access_token>`、`Content-Type: application/json`
**Payload：** `{"password":"current-password","code":"123456"}`。
**Path／Query Parameters：** 無。

**Success：`200 OK`**

```json
{"data":{"recovery_codes":["XXXXX-XXXXX","...共 10 組"]}}
```

**Errors：** `AUTH_INVALID_CREDENTIALS`、`AUTH_MFA_INVALID_CODE`、`AUTH_TOKEN_INVALID`。
**Security：** 舊 Recovery Codes 全部失效；新 Codes 僅此一次明文回傳。

## 8. Email、密碼與高權限帳號復原

### POST /v1/auth/email/verify/request

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"email":"alice@example.com"}`。
**Path／Query Parameters：** 無。
**Success：** `202 Accepted`，`{"data":{"accepted":true}}`。
**Errors：** 空白或非法 Payload 為 `COMMON_VALIDATION_FAILED`。
**Security：** Generic Response；Email 是否存在、是否已驗證或寄送是否成功都不可由 Response 判斷。

### POST /v1/auth/email/verify/confirm

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"token":"ev_opaque_value"}`。
**Path／Query Parameters：** 無。
**Success：** `200 OK`，`{"data":{"verified":true}}`。
**Errors：** `AUTH_RECOVERY_TOKEN_INVALID`、`COMMON_VALIDATION_FAILED`。
**Security：** Token 短效、一次性，完成後不可重用。

### POST /v1/auth/password/reset/request

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"email":"alice@example.com"}`。
**Path／Query Parameters：** 無。
**Success：** `202 Accepted`，`{"data":{"accepted":true}}`。
**Errors：** 空白或非法 Payload 為 `COMMON_VALIDATION_FAILED`。
**Security：** Generic Response，避免帳號枚舉。

### POST /v1/auth/password/reset/confirm

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"token":"pr_opaque_value","new_password":"new-secure-password"}`。
**Path／Query Parameters：** 無。
**Success：** `200 OK`，`{"data":{"reset":true}}`。
**Errors：** `AUTH_RECOVERY_TOKEN_INVALID`、`AUTH_PASSWORD_COMPROMISED`、`COMMON_VALIDATION_FAILED`。
**Security：** 成功後撤銷該帳號既有 Refresh Token；新密碼不得出現在已知外洩清單。

### POST /v1/auth/privileged-recovery/request

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"tenant":"","username":"staff-user"}`。
**Path／Query Parameters：** 無。
**Success：** `200 OK`，`{"data":{}}`。
**Errors：** Payload 無效為 `COMMON_VALIDATION_FAILED`。
**Security：** Generic Response；帳號是否存在或是否為高權限帳號不可辨識。

### POST /v1/auth/privileged-recovery/complete

以 Email Token 加既有 Recovery Code 完成高權限帳號 MFA 復原。

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"token":"pvr_opaque_value","recovery_code":"XXXXX-XXXXX"}`。
**Path／Query Parameters：** 無。
**Success：** `200 OK`，`{"data":{}}`。
**Errors：** `AUTH_PRIVILEGED_RECOVERY_INVALID`、`COMMON_VALIDATION_FAILED`。
**Security：** Token 與 Recovery Code 都必須有效；任何失敗收斂為同一錯誤，避免側信道。

### POST /v1/auth/privileged-recovery/complete-with-approval

以 Email Token 加營運方已核准狀態完成復原。

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"token":"pvr_opaque_value"}`。
**Path／Query Parameters：** 無。
**Success：** `200 OK`，`{"data":{}}`。
**Errors：** `AUTH_PRIVILEGED_RECOVERY_INVALID`、`COMMON_VALIDATION_FAILED`。
**Security：** 未核准、過期、已使用或錯誤 Token 皆回相同錯誤。

## 9. S2S 帳號供應

S2S 端點只能由平台後端呼叫。每個請求都要同時帶 platform code 與該 Realm 的 API Key。

### POST /v1/internal/accounts

**Headers**

| 名稱 | 必要 | 值 |
|---|---|---|
| `X-Session-Platform-Code` | 是 | `<platform_code>` |
| `Authorization` | 是 | `Bearer <sk_API_KEY>` |
| `Content-Type` | 是 | `application/json` |

**Path／Query Parameters：** 無。

**Payload**

| 欄位 | 型別 | 必要 | 說明 |
|---|---|---|---|
| `tenant` | string | 是 | 無租戶時傳 `""` |
| `type` | string | 是 | `member` 或 `staff` |
| `username` | string | 是 | 平台內帳號名稱 |
| `password` | string | 是 | 初始密碼，最大 1024 字元 |

```json
{"tenant":"","type":"member","username":"alice","password":"S3cure-Pass!"}
```

**Success：`201 Created`**

```json
{"data":{"sub":"acc_01..."}}
```

**Errors：** `AUTH_TOKEN_INVALID`、`AUTH_PLATFORM_UNKNOWN`、`COMMON_IDEMPOTENCY_CONFLICT`、`COMMON_VALIDATION_FAILED`。
**Security：** `sub` 是接入方連結業務資料的穩定識別；不得儲存明文密碼。API Key 跨 Realm 使用一律拒絕。

### PATCH /v1/internal/accounts/{sub}

對帳號執行停用／啟用、重設密碼或緊急撤銷，三者只能選一個。

**Headers：** 同帳號供應端點。
**Path Parameters：** `sub`，`acc_` 開頭的帳號識別。
**Query Parameters：** 無。

**Payload，三選一**

```json
{"status":"disabled"}
```

```json
{"reset_password":"new-secure-password"}
```

```json
{"revoke_all":true}
```

`status` 只接受 `active` 或 `disabled`。

**Success：`200 OK`**

```json
{"data":{"sub":"acc_01...","applied":true}}
```

**Errors：** `COMMON_NOT_FOUND`、`COMMON_VALIDATION_FAILED`、`AUTH_TOKEN_INVALID`。
**Security：** 停用帳號會撤銷 Refresh Token；`revoke_all` 用於疑似帳號遭竊的緊急處置。

## 10. 健康檢查

### GET /livez

**Headers／Path／Query／Payload：** 無。
**認證：** 無。
**Success：** `200 OK`，`{"status":"live"}`。
**用途：** Process 存活檢查，不代表資料庫已就緒。

### GET /readyz

**Headers／Path／Query／Payload：** 無。
**認證：** 無。
**Success：** `200 OK`，`{"status":"ready"}`。
**Not Ready：** `503 Service Unavailable`，`{"status":"not_ready"}`。
**用途：** 驗證服務依賴是否可用。

## 11. Token 與安全規範

| 憑證 | 形式 | 核心規範 |
|---|---|---|
| `/v1` Access Token | RS256 JWT | 本地 JWKS 驗章；驗 `iss`、`aud`、`exp`、`typ` |
| `/v1` Refresh Token | `rt_...` 不透明值 | 輪替；重用觸發整帳號撤銷 |
| OAuth Access Token | `typ=at+jwt` RS256 JWT | Realm issuer；預設短效 |
| OAuth ID Token | RS256 JWT | 驗 `aud == client_id`、`nonce`、`iss`、`exp` |
| OAuth Refresh Token | Selector + Secret 不透明值 | 綁定 client 與 session，每次使用輪替 |
| Authorization Code | 不透明值 | 短效、一次性、綁定 redirect URI 與 PKCE |
| `mfa_token` | `mfa_...` | 5 分鐘、一次性 |
| Recovery Code | `XXXXX-XXXXX` | 一次性，只在產生時顯示 |
| S2S API Key | `sk_...` | 僅後端保存、Realm-scoped |

客戶端必須：

1. 只接受 `RS256`，拒絕 `alg=none`、HMAC 混淆與未知演算法。
2. 驗證 Token 的 issuer、audience、expiry、type 與必要 nonce。
3. 不將密碼、Token、API Key、MFA Secret、Recovery Code 寫入 Log。
4. 對 `429` 依 `Retry-After` 退避；對一般 `4xx` 不自動重試。
5. 對 OAuth Redirect URI 採 Exact Match，不自行正規化尾斜線。
6. Access Token 優先放記憶體；若使用 Cookie，必須使用 `HttpOnly`、`Secure` 與合適 `SameSite`。

## 12. 錯誤碼

| id | code | HTTP | 說明 |
|---:|---|---:|---|
| 1000 | `COMMON_INTERNAL_ERROR` | 500 | 內部錯誤，憑 `trace_id` 回報 |
| 1001 | `COMMON_VALIDATION_FAILED` | 422 | JSON、欄位、型別或限制不符 |
| 1002 | `COMMON_NOT_FOUND` | 404 | 資源或路徑不存在 |
| 1003 | `COMMON_RATE_LIMITED` | 429 | 請依 `Retry-After` 退避 |
| 1004 | `COMMON_IDEMPOTENCY_CONFLICT` | 409 | 唯一資源已存在 |
| 1005 | `COMMON_FORBIDDEN` | 403 | 已驗證但權限不足 |
| 2001 | `AUTH_INVALID_CREDENTIALS` | 401 | 帳號或密碼錯誤 |
| 2002 | `AUTH_ACCOUNT_DISABLED` | 403 | 帳號停用 |
| 2003 | `AUTH_ACCOUNT_LOCKED` | 423 | 多次登入失敗後暫時鎖定 |
| 2004 | `AUTH_MFA_REQUIRED` | 401 | 流程需要 MFA |
| 2005 | `AUTH_MFA_INVALID_CODE` | 401 | TOTP 或 challenge 無效 |
| 2006 | `AUTH_MFA_ALREADY_ENABLED` | 409 | MFA 已啟用 |
| 2007 | `AUTH_RECOVERY_CODE_INVALID` | 401 | Recovery Code 無效或已使用 |
| 2008 | `AUTH_REFRESH_INVALID` | 401 | Refresh Token 無效或過期 |
| 2009 | `AUTH_REFRESH_REUSED` | 401 | 偵測到 Refresh Token 重用 |
| 2010 | `AUTH_TOKEN_EXPIRED` | 401 | Access Token 已過期 |
| 2011 | `AUTH_TOKEN_INVALID` | 401 | JWT、API Key 或 Bearer 格式無效 |
| 2012 | `AUTH_TOKEN_REVOKED` | 401 | Token 已緊急撤銷 |
| 2013 | `AUTH_PLATFORM_UNKNOWN` | 400 | Platform code 無法解析、未知或停權 |
| 2014 | `AUTH_RECOVERY_TOKEN_INVALID` | 401 | Email／密碼復原 Token 無效、過期或已使用 |
| 2015 | `AUTH_PASSWORD_COMPROMISED` | 422 | 密碼存在於已知外洩清單 |
| 2016 | `AUTH_MFA_SETUP_REQUIRED` | 403 | 高權限流程尚未完成 MFA 設定 |
| 2017 | `AUTH_PRIVILEGED_RECOVERY_INVALID` | 401 | 高權限 MFA 復原請求無效 |

## 13. 最小串接檢查

```bash
# 存活
curl https://identity.lifeintent.app/livez

# Realm Discovery
curl https://identity.lifeintent.app/realms/<slug>/.well-known/openid-configuration

# /v1 JWKS
curl https://identity.lifeintent.app/v1/.well-known/jwks.json \
  -H "X-Session-Platform-Code: <platform_code>"
```

若上述請求成功，接著依使用情境選擇：

- 標準第三方登入：OAuth Authorization Code + PKCE。
- 自家平台帳密登入：`POST /v1/auth/login`。
- 後端帳號供應：`POST /v1/internal/accounts`。

完整端到端流程另見 `INTEGRATION.md`。
