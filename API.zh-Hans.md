# Identity Service 公开 API 文件

> Base URL：`https://identity.lifeintent.app`
> 文件更新：2026-07-20（Asia/Taipei）
> 适用对象：接入平台的前端、后端、Resource Server 与 AI 开发代理人。
> 公开范围不包含营运者专用 `/v1/admin/*` 与系统 Webhook `/webhooks/*`。

## 1. 共通规范

Identity Service 提供两组 API：

- `/realms/{slug}/*`：标准 OIDC/OAuth 2.0，Realm 已包含在 URL，不使用 `X-Session-Platform-Code`。
- `/v1/*`：平台登入、帐号自助、MFA 与 S2S 帐号供应，每次请求必须带 `X-Session-Platform-Code`。

| 项目 | 规范 |
|---|---|
| TLS | 全部端点只使用 HTTPS |
| JSON | UTF-8；一般有 Payload 的端点使用 `application/json` |
| OAuth Form | `/oauth/token`、`/oauth/revoke`、`/oauth/introspect` 使用 `application/x-www-form-urlencoded` |
| 未知 JSON 栏位 | 拒绝并回验证错误 |
| Request Body 上限 | 64 KiB |
| 时间 | JWT 时间栏位使用 Unix timestamp（秒） |
| 管理 API | `/v1/admin/*` 不属于公开串接范围 |

## 2. Headers

| Header | 适用范围 | 必要性 | 格式与限制 |
|---|---|---|---|
| `Content-Type` | 有 Payload 的请求 | 必要 | 一般 API：`application/json`；OAuth form 端点：`application/x-www-form-urlencoded` |
| `Accept` | 全部 | 选用 | 建议 `application/json` |
| `Accept-Language` | `/v1/*` | 选用 | `zh-TW` 或 `en`；其他值以英文回退 |
| `X-Session-Platform-Code` | `/v1/*` | 必要 | 营运方核发的 platform code／realm slug，例如 `topinkiwi` |
| `Authorization` | Bearer JWT、S2S API Key | 依端点 | `Bearer <access_token>` 或 `Bearer <sk_API_KEY>` |
| `X-Request-Id` | 全部 | 选用 | 1–128 字元，只接受英数字、`.`、`_`、`-`；合法值会在 Response Header 回传 |

注意：

- `/realms/{slug}/*` 不需要 `X-Session-Platform-Code`。
- `/v1/*` 即使没有认证，也必须带 `X-Session-Platform-Code`。
- S2S API Key 只能放在后端 Secret 管理系统，不得放入浏览器、Mobile App、原始码或 Log。
- 错误 Response 的 `trace_id` 对应 `X-Request-Id`，回报问题时请一并提供。

## 3. Response 与错误格式

### 3.1 `/v1` 成功格式

除 `204 No Content` 外，成功资料包在 `data`：

```json
{
  "data": {
    "example": true
  }
}
```

### 3.2 `/v1` 错误格式

```json
{
  "error": {
    "code": "COMMON_VALIDATION_FAILED",
    "id": 1001,
    "message": "请求格式或栏位无效",
    "trace_id": "5b5aa30b-00fd-46ab-a836-322c779ff2c8"
  }
}
```

程式判断使用稳定字串 `code`；`message` 只供显示。`429 COMMON_RATE_LIMITED` 会附 `Retry-After` Response Header，客户端应依秒数等待并采指数退避。

### 3.3 OAuth 错误格式

`/realms/{slug}/oauth/*` 遵循 OAuth JSON 错误，不使用 `/v1` envelope：

```json
{
  "error": "invalid_grant",
  "error_description": "the authorization grant is invalid"
}
```

OAuth Token 与敏感资料回应带 `Cache-Control: no-store`、`Pragma: no-cache`。

## 4. OIDC Discovery 与 JWKS

### GET /realms/{slug}/.well-known/openid-configuration

取得 Realm 的 OIDC metadata。

**Headers：** `Accept: application/json`（选用）
**Path Parameters：** `slug`，营运方核发的 Realm slug。
**Query Parameters：** 无。
**Payload：** 无。
**认证：** 无。

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

**Errors：** Realm 不存在、停权或 slug 格式非法均回相同 `404 COMMON_NOT_FOUND`，避免泄漏 Realm 状态。
**Security：** 以回传的 endpoint 为准，不要自行拼接或改成 `/v1/realms/*`。

### GET /realms/{slug}/.well-known/jwks.json

取得该 Realm 的 RS256 公开验章金钥。

**Headers：** `Accept: application/json`（选用）
**Path Parameters：** `slug`。
**Query Parameters：** 无。
**Payload：** 无。
**认证：** 无。

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

**Errors：** 与 Discovery 相同。
**Security：** JWKS 只含公开材料；验章时依 JWT header 的 `kid` 选钥，且只接受 `RS256`。

## 5. OAuth 2.0 Authorization Code + PKCE

所有端点使用 `/realms/{slug}`，不带 `X-Session-Platform-Code`。Public client 无 Client Secret，必须使用 PKCE `S256`。

### POST /realms/{slug}/oauth/authorize

建立短效、一次性的授权交易。

**Headers**

| 名称 | 必要 | 值 |
|---|---|---|
| `Content-Type` | 是 | `application/json` |

**Path Parameters：** `slug`。
**Query Parameters：** 无。

**Payload**

| 栏位 | 型别 | 必要 | 限制 |
|---|---|---|---|
| `response_type` | string | 是 | 固定 `code` |
| `client_id` | string | 是 | 营运方登记的 client ID |
| `redirect_uri` | string | 是 | 必须与登记值 Exact Match |
| `scope` | string | 是 | 空白分隔；需包含允许的 scope |
| `state` | string | 是 | Client 产生的高熵随机值 |
| `nonce` | string | 是 | Client 产生，之后验证 ID Token |
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

**Errors：** `invalid_request`、`unauthorized_client`、`invalid_scope`；Realm 不存在或停权为不可区分的 `404 invalid_request`。
**Security：** `state`、`nonce`、`code_verifier` 必须由 CSPRNG 产生；不得记录密码或交易 handle。

### POST /realms/{slug}/oauth/authorize/login

以帐密完成授权交易；若帐号已启用 MFA，先回 MFA challenge。

**Headers：** `Content-Type: application/json`
**Path Parameters：** `slug`。
**Query Parameters：** 无。

**Payload**

| 栏位 | 型别 | 必要 | 说明 |
|---|---|---|---|
| `transaction` | string | 是 | authorize 回传的一次性交易 handle |
| `tenant` | string | 是 | 无租户时传空字串 |
| `username` | string | 是 | 使用者帐号 |
| `password` | string | 是 | 使用者密码 |

```json
{
  "transaction": "txn_opaque_value",
  "tenant": "",
  "username": "alice",
  "password": "S3cure-Pass!"
}
```

**Success A：`200 OK`，无 MFA**

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
**Security：** Client 收到结果后必须比对 `state`，授权码短效且一次性。

### POST /realms/{slug}/oauth/authorize/mfa

以 MFA challenge 与 TOTP 完成授权交易。

**Headers：** `Content-Type: application/json`
**Path Parameters：** `slug`。
**Query Parameters：** 无。

**Payload**

```json
{
  "transaction": "txn_opaque_value",
  "mfa_token": "mfa_opaque_value",
  "code": "123456"
}
```

三个栏位皆为必要 string；`code` 为验证器当下的 6 位数。

**Success：`200 OK`**

```json
{
  "code": "authorization-code",
  "state": "random-state",
  "redirect_uri": "https://app.example.com/callback"
}
```

**Errors：** `invalid_grant`、`invalid_transaction`、`access_denied`。
**Security：** `transaction`、`mfa_token` 与 TOTP challenge 均短效且一次性。

### POST /realms/{slug}/oauth/token

以 Authorization Code + PKCE 或 Refresh Token 取得 Token。

**Headers：** `Content-Type: application/x-www-form-urlencoded`
**Path Parameters：** `slug`。
**Query Parameters：** 无。
**认证：** Public client 不使用 Client Secret。

**Authorization Code Payload**

| 栏位 | 必要 | 值 |
|---|---|---|
| `grant_type` | 是 | `authorization_code` |
| `code` | 是 | 上一步取得的一次性授权码 |
| `redirect_uri` | 是 | 必须与 authorize 时完全相同 |
| `client_id` | 是 | 登记的 client ID |
| `code_verifier` | 是 | 对应原 `code_challenge` 的 PKCE verifier |

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

| 栏位 | 必要 | 值 |
|---|---|---|
| `grant_type` | 是 | `refresh_token` |
| `refresh_token` | 是 | 最近一次取得的 OAuth Refresh Token |
| `client_id` | 是 | 原 client ID |

Refresh 成功回新的 `access_token`、`refresh_token`、`token_type`、`expires_in`、`scope`，不回新的 `id_token`。

**Errors：** `invalid_request`、`invalid_client`、`invalid_grant`、`unsupported_grant_type`。
**Security：** Refresh Token 每次使用后轮替；只能保留最新一张。Authorization Code 验证失败后不得重用。

### POST /realms/{slug}/oauth/revoke

撤销 Access 或 Refresh Token，遵循 RFC 7009。

**Headers：** `Content-Type: application/x-www-form-urlencoded`
**Path Parameters：** `slug`。
**Query Parameters：** 无。

**Payload**

| 栏位 | 必要 | 说明 |
|---|---|---|
| `token` | 是 | 要撤销的 Token |
| `client_id` | 是 | Token 所属 client |

**Success：`200 OK`**

```json
{}
```

Token 是否存在皆回相同成功结果。
**Errors：** Client 不存在或停权回 `401 invalid_client`；格式错误回 `invalid_request`。
**Security：** 不得依 Response 推断 Token 是否曾存在。

### POST /realms/{slug}/oauth/introspect

Resource Server 以 S2S API Key 查询 Token 状态，遵循 RFC 7662。

**Headers**

| 名称 | 必要 | 值 |
|---|---|---|
| `Authorization` | 是 | `Bearer <sk_API_KEY>` |
| `Content-Type` | 是 | `application/x-www-form-urlencoded` |

**Path Parameters：** `slug`。
**Query Parameters：** 无。
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

**Errors：** 缺少、错误或跨 Realm API Key 一律回相同 `401 invalid_client`。
**Security：** 一般请求优先本地 JWKS 验章；只有需要即时撤销状态时使用 Introspection。

## 6. 登入与 Session

本章所有 `/v1/*` 端点都要带 `X-Session-Platform-Code`。

### POST /v1/auth/login

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Path Parameters：** 无。
**Query Parameters：** 无。

**Payload**

| 栏位 | 型别 | 必要 | 说明 |
|---|---|---|---|
| `username` | string | 是 | 帐号 |
| `password` | string | 是 | 密码 |
| `tenant` | string | 是 | 无租户时传 `""` |

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
**Security：** Response 带 `Cache-Control: no-store`；帐号不存在与密码错误不可区分。

### POST /v1/auth/refresh

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Path／Query Parameters：** 无。

**Payload**

```json
{"refresh_token":"rt_..."}
```

**Success：`200 OK`**

```json
{"data":{"access_token":"eyJ...","refresh_token":"rt_new...","expires_in":2700}}
```

**Errors：** `AUTH_REFRESH_INVALID`、`AUTH_REFRESH_REUSED`、`COMMON_VALIDATION_FAILED`。
**Security：** Refresh Token 每次换发立即轮替；重用旧 Token 会撤销该帐号所有 Refresh Token。

### POST /v1/auth/logout

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Path／Query Parameters：** 无。
**Payload：** `{"refresh_token":"rt_..."}`。
**Success：`204 No Content`，无 Response body。
**Errors：** Payload 无效时为 `COMMON_VALIDATION_FAILED`。
**Security：** 有效或不存在的 Token 不应造成可辨识差异。

### GET /v1/.well-known/jwks.json

取得 platform profile 的公开验章金钥。

**Headers：** `X-Session-Platform-Code`
**Path／Query Parameters：** 无。
**Payload：** 无。
**Success：** `200 OK`，格式同 Realm JWKS，`Cache-Control: public, max-age=300`。
**Errors：** `AUTH_PLATFORM_UNKNOWN`、`COMMON_INTERNAL_ERROR`。
**Security：** `/v1` Access Token 验证需同时检核 RS256 签章、`iss`、`aud`、`exp` 与允许的 `typ`。

## 7. MFA

### POST /v1/auth/mfa/verify

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"mfa_token":"mfa_...","code":"123456"}`。
**Path／Query Parameters：** 无。
**Success：** `200 OK`，回 TokenResponse。
**Errors：** `AUTH_MFA_INVALID_CODE`、`COMMON_VALIDATION_FAILED`。
**Security：** `mfa_token` 5 分钟、一次性；验证失败也会消耗。

### POST /v1/auth/mfa/recovery

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"mfa_token":"mfa_...","recovery_code":"XXXXX-XXXXX"}`。
**Path／Query Parameters：** 无。
**Success：** `200 OK`，回 TokenResponse。
**Errors：** `AUTH_RECOVERY_CODE_INVALID`、`AUTH_MFA_INVALID_CODE`、`COMMON_VALIDATION_FAILED`。
**Security：** 备援码使用后立即失效。

### POST /v1/auth/mfa/setup

**Headers：** `X-Session-Platform-Code`、`Authorization: Bearer <access_token>`
**Content-Type／Payload：** 无。
**Path／Query Parameters：** 无。

**Success：`200 OK`**

```json
{"data":{"secret":"BASE32SECRET","otpauth_uri":"otpauth://totp/..."}}
```

**Errors：** `AUTH_TOKEN_INVALID`、`AUTH_TOKEN_EXPIRED`、`AUTH_TOKEN_REVOKED`、`AUTH_MFA_ALREADY_ENABLED`。
**Security：** `secret` 只用于当次绑定画面，不得写入 Log。

### POST /v1/auth/mfa/activate

**Headers：** `X-Session-Platform-Code`、`Authorization: Bearer <access_token>`、`Content-Type: application/json`
**Payload：** `{"code":"123456"}`。
**Path／Query Parameters：** 无。

**Success：`200 OK`**

```json
{"data":{"enabled":true,"recovery_codes":["XXXXX-XXXXX","...共 10 组"]}}
```

**Errors：** `AUTH_MFA_INVALID_CODE`、`AUTH_TOKEN_INVALID`、`COMMON_VALIDATION_FAILED`。
**Security：** Recovery Codes 仅此一次明文回传，Client 必须立即交付使用者安全保存。

### POST /v1/auth/mfa/disable

**Headers：** `X-Session-Platform-Code`、`Authorization: Bearer <access_token>`、`Content-Type: application/json`
**Payload：** `{"password":"current-password","code":"123456"}`。
**Path／Query Parameters：** 无。
**Success：** `200 OK`，`{"data":{"enabled":false}}`。
**Errors：** `AUTH_INVALID_CREDENTIALS`、`AUTH_MFA_INVALID_CODE`、`AUTH_TOKEN_INVALID`。
**Security：** 停用会使既有 Recovery Codes 作废。

### POST /v1/auth/mfa/recovery-codes/regenerate

**Headers：** `X-Session-Platform-Code`、`Authorization: Bearer <access_token>`、`Content-Type: application/json`
**Payload：** `{"password":"current-password","code":"123456"}`。
**Path／Query Parameters：** 无。

**Success：`200 OK`**

```json
{"data":{"recovery_codes":["XXXXX-XXXXX","...共 10 组"]}}
```

**Errors：** `AUTH_INVALID_CREDENTIALS`、`AUTH_MFA_INVALID_CODE`、`AUTH_TOKEN_INVALID`。
**Security：** 旧 Recovery Codes 全部失效；新 Codes 仅此一次明文回传。

## 8. 注册、Email、密码与高权限帐号复原

### POST /v1/auth/register

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"email":"alice@example.com","password":"correct-horse-battery"}`。
**Path／Query Parameters：** 无。

**Success：`202 Accepted`**

```json
{"data":{"accepted":true}}
```

**Errors：** Email／密码格式或 Realm 不允许自助注册为 `COMMON_VALIDATION_FAILED`；已知外泄密码为 `AUTH_PASSWORD_COMPROMISED`；共享配额超限为 `COMMON_RATE_LIMITED`。
**Security：** 成功与同 Realm 等价 Email 已存在回完全相同的状态与 Body。密码必须为 12～128 个 Unicode 字元；Account、Credential、Primary Email 与 Required Action 同一 Transaction 建立。只允许要求 Email 验证、允许 pending 且不要求 MFA 才能启用的 member Realm；`system` Realm 一律拒绝。注册后寄信若暂时失败，可安全呼叫重寄端点补偿。所有 Lambda Runtime 共用 PostgreSQL 双层限制：同 Realm／IP 预设 5 次每 10 分钟、单一 Realm 预设 100 次每分钟；只落地 IP 的 HMAC。

### POST /v1/auth/email/verify/request

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"email":"alice@example.com"}`。
**Path／Query Parameters：** 无。
**Success：** `202 Accepted`，`{"data":{"accepted":true}}`。
**Errors：** 空白或非法 Payload 为 `COMMON_VALIDATION_FAILED`。
**Security：** Generic Response；Email 是否存在、是否已验证、是否被帐号级限流或寄送是否成功都不可由 Response 判断。同帐号、同用途的限制预设为 1 分钟冷却、每小时 5 次、24 小时 10 次；成功重寄时旧 Token 立即失效。

### POST /v1/auth/email/verify/confirm

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"token":"evt_opaque_value"}`。
**Path／Query Parameters：** 无。
**Success：** `200 OK`，`{"data":{"verified":true}}`。
**Errors：** `AUTH_RECOVERY_TOKEN_INVALID`、`COMMON_VALIDATION_FAILED`。
**Security：** Token 短效、一次性且绑定 Realm，完成后不可重用。若 `verify_email` 是最后一个 Required Action，Email、Action 与帐号启用在同一 Transaction 落地。

### POST /v1/auth/password/reset/request

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"email":"alice@example.com"}`。
**Path／Query Parameters：** 无。
**Success：** `202 Accepted`，`{"data":{"accepted":true}}`。
**Errors：** 空白或非法 Payload 为 `COMMON_VALIDATION_FAILED`。
**Security：** Generic Response，避免帐号枚举；与验证信共用帐号级原子限流政策，但依 `password_reset` 用途独立计数。成功重寄时旧 Token 立即失效。

### POST /v1/auth/password/reset/confirm

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"token":"pr_opaque_value","new_password":"new-secure-password"}`。
**Path／Query Parameters：** 无。
**Success：** `200 OK`，`{"data":{"reset":true}}`。
**Errors：** `AUTH_RECOVERY_TOKEN_INVALID`、`AUTH_PASSWORD_COMPROMISED`、`COMMON_VALIDATION_FAILED`。
**Security：** 成功后撤销该帐号既有 Refresh Token；新密码不得出现在已知外泄清单。

### POST /v1/auth/privileged-recovery/request

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"tenant":"","username":"staff-user"}`。
**Path／Query Parameters：** 无。
**Success：** `200 OK`，`{"data":{}}`。
**Errors：** Payload 无效为 `COMMON_VALIDATION_FAILED`。
**Security：** Generic Response；帐号是否存在或是否为高权限帐号不可辨识。只有具备已验证 Primary Email 的高权限帐号才会建立请求并寄送 Token；Email Sender 未设定时此组端点不挂载。

### POST /v1/auth/privileged-recovery/complete

以 Email Token 加既有 Recovery Code 完成高权限帐号 MFA 复原。

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"token":"pvr_opaque_value","recovery_code":"XXXXX-XXXXX"}`。
**Path／Query Parameters：** 无。
**Success：** `200 OK`，`{"data":{}}`。
**Errors：** `AUTH_PRIVILEGED_RECOVERY_INVALID`、`COMMON_VALIDATION_FAILED`。
**Security：** Token 与 Recovery Code 都必须有效；任何失败收敛为同一错误，避免侧信道。

### POST /v1/auth/privileged-recovery/complete-with-approval

以 Email Token 加营运方已核准状态完成复原。

**Headers：** `X-Session-Platform-Code`、`Content-Type: application/json`
**Payload：** `{"token":"pvr_opaque_value"}`。
**Path／Query Parameters：** 无。
**Success：** `200 OK`，`{"data":{}}`。
**Errors：** `AUTH_PRIVILEGED_RECOVERY_INVALID`、`COMMON_VALIDATION_FAILED`。
**Security：** 未核准、过期、已使用或错误 Token 皆回相同错误。

## 9. S2S 帐号供应

S2S 端点只能由平台后端呼叫。每个请求都要同时带 platform code 与该 Realm 的 API Key。

### POST /v1/internal/accounts

**Headers**

| 名称 | 必要 | 值 |
|---|---|---|
| `X-Session-Platform-Code` | 是 | `<platform_code>` |
| `Authorization` | 是 | `Bearer <sk_API_KEY>` |
| `Content-Type` | 是 | `application/json` |

**Path／Query Parameters：** 无。

**Payload**

| 栏位 | 型别 | 必要 | 说明 |
|---|---|---|---|
| `tenant` | string | 是 | 无租户时传 `""` |
| `type` | string | 是 | `member` 或 `staff` |
| `username` | string | 是 | 平台内帐号名称 |
| `password` | string | 是 | 初始密码，最大 1024 字元 |

```json
{"tenant":"","type":"member","username":"alice","password":"S3cure-Pass!"}
```

**Success：`201 Created`**

```json
{"data":{"sub":"acc_01..."}}
```

**Errors：** `AUTH_TOKEN_INVALID`、`AUTH_PLATFORM_UNKNOWN`、`COMMON_IDEMPOTENCY_CONFLICT`、`COMMON_VALIDATION_FAILED`。
**Security：** `sub` 是接入方连结业务资料的稳定识别；不得储存明文密码。API Key 跨 Realm 使用一律拒绝。

### PATCH /v1/internal/accounts/{sub}

对帐号执行停用／启用、重设密码或紧急撤销，三者只能选一个。

**Headers：** 同帐号供应端点。
**Path Parameters：** `sub`，`acc_` 开头的帐号识别。
**Query Parameters：** 无。

**Payload，三选一**

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
**Security：** 停用帐号会撤销 Refresh Token；`revoke_all` 用于疑似帐号遭窃的紧急处置。

## 10. 健康检查

### GET /livez

**Headers／Path／Query／Payload：** 无。
**认证：** 无。
**Success：** `200 OK`，`{"status":"live"}`。
**用途：** Process 存活检查，不代表资料库已就绪。

### GET /readyz

**Headers／Path／Query／Payload：** 无。
**认证：** 无。
**Success：** `200 OK`，`{"status":"ready"}`。
**Not Ready：** `503 Service Unavailable`，`{"status":"not_ready"}`。
**用途：** 验证服务依赖是否可用。

## 11. Token 与安全规范

| 凭证 | 形式 | 核心规范 |
|---|---|---|
| `/v1` Access Token | RS256 JWT | 本地 JWKS 验章；验 `iss`、`aud`、`exp`、`typ` |
| `/v1` Refresh Token | `rt_...` 不透明值 | 轮替；重用触发整帐号撤销 |
| OAuth Access Token | `typ=at+jwt` RS256 JWT | Realm issuer；预设短效 |
| OAuth ID Token | RS256 JWT | 验 `aud == client_id`、`nonce`、`iss`、`exp` |
| OAuth Refresh Token | Selector + Secret 不透明值 | 绑定 client 与 session，每次使用轮替 |
| Authorization Code | 不透明值 | 短效、一次性、绑定 redirect URI 与 PKCE |
| `mfa_token` | `mfa_...` | 5 分钟、一次性 |
| Recovery Code | `XXXXX-XXXXX` | 一次性，只在产生时显示 |
| S2S API Key | `sk_...` | 仅后端保存、Realm-scoped |

客户端必须：

1. 只接受 `RS256`，拒绝 `alg=none`、HMAC 混淆与未知演算法。
2. 验证 Token 的 issuer、audience、expiry、type 与必要 nonce。
3. 不将密码、Token、API Key、MFA Secret、Recovery Code 写入 Log。
4. 对 `429` 依 `Retry-After` 退避；对一般 `4xx` 不自动重试。
5. 对 OAuth Redirect URI 采 Exact Match，不自行正规化尾斜线。
6. Access Token 优先放记忆体；若使用 Cookie，必须使用 `HttpOnly`、`Secure` 与合适 `SameSite`。

## 12. 错误码

| id | code | HTTP | 说明 |
|---:|---|---:|---|
| 1000 | `COMMON_INTERNAL_ERROR` | 500 | 内部错误，凭 `trace_id` 回报 |
| 1001 | `COMMON_VALIDATION_FAILED` | 422 | JSON、栏位、型别或限制不符 |
| 1002 | `COMMON_NOT_FOUND` | 404 | 资源或路径不存在 |
| 1003 | `COMMON_RATE_LIMITED` | 429 | 请依 `Retry-After` 退避 |
| 1004 | `COMMON_IDEMPOTENCY_CONFLICT` | 409 | 唯一资源已存在 |
| 1005 | `COMMON_FORBIDDEN` | 403 | 已验证但权限不足 |
| 2001 | `AUTH_INVALID_CREDENTIALS` | 401 | 帐号或密码错误 |
| 2002 | `AUTH_ACCOUNT_DISABLED` | 403 | 帐号停用 |
| 2003 | `AUTH_ACCOUNT_LOCKED` | 423 | 多次登入失败后暂时锁定 |
| 2004 | `AUTH_MFA_REQUIRED` | 401 | 流程需要 MFA |
| 2005 | `AUTH_MFA_INVALID_CODE` | 401 | TOTP 或 challenge 无效 |
| 2006 | `AUTH_MFA_ALREADY_ENABLED` | 409 | MFA 已启用 |
| 2007 | `AUTH_RECOVERY_CODE_INVALID` | 401 | Recovery Code 无效或已使用 |
| 2008 | `AUTH_REFRESH_INVALID` | 401 | Refresh Token 无效或过期 |
| 2009 | `AUTH_REFRESH_REUSED` | 401 | 侦测到 Refresh Token 重用 |
| 2010 | `AUTH_TOKEN_EXPIRED` | 401 | Access Token 已过期 |
| 2011 | `AUTH_TOKEN_INVALID` | 401 | JWT、API Key 或 Bearer 格式无效 |
| 2012 | `AUTH_TOKEN_REVOKED` | 401 | Token 已紧急撤销 |
| 2013 | `AUTH_PLATFORM_UNKNOWN` | 400 | Platform code 无法解析、未知或停权 |
| 2014 | `AUTH_RECOVERY_TOKEN_INVALID` | 401 | Email／密码复原 Token 无效、过期或已使用 |
| 2015 | `AUTH_PASSWORD_COMPROMISED` | 422 | 密码存在于已知外泄清单 |
| 2016 | `AUTH_MFA_SETUP_REQUIRED` | 403 | 高权限流程尚未完成 MFA 设定 |
| 2017 | `AUTH_PRIVILEGED_RECOVERY_INVALID` | 401 | 高权限 MFA 复原请求无效 |

## 13. 最小串接检查

```bash
# 存活
curl https://identity.lifeintent.app/livez

# Realm Discovery
curl https://identity.lifeintent.app/realms/<slug>/.well-known/openid-configuration

# /v1 JWKS
curl https://identity.lifeintent.app/v1/.well-known/jwks.json \
  -H "X-Session-Platform-Code: <platform_code>"
```

若上述请求成功，接著依使用情境选择：

- 标准第三方登入：OAuth Authorization Code + PKCE。
- 自家平台帐密登入：`POST /v1/auth/login`。
- 后端帐号供应：`POST /v1/internal/accounts`。

完整端到端流程另见 `INTEGRATION.md`。
