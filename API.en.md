# Identity Service Public API Documentation

> Base URL: `https://identity.lifeintent.app`
> Last updated: 2026-07-20 (Asia/Taipei)
> Applicable audience: Front-end, back-end, Resource Server, and AI development agents accessing the platform.
> The public scope excludes operator-only `/v1/admin/*` and system webhook `/webhooks/*`.

## 1. Common Conventions

Identity Service provides two sets of APIs:

- `/realms/{slug}/*`: Standard OIDC/OAuth 2.0, Realm is included in the URL, `X-Session-Platform-Code` is not used.
- `/v1/*`: platform login, account self-service, MFA, and S2S account provisioning. Every request must include `X-Session-Platform-Code`.

| Item | Requirement |
|---|---|
| TLS | All endpoints use HTTPS only |
| JSON | UTF-8; Common Payload Endpoints Use `application/json` |
| OAuth Form | `/oauth/token`, `/oauth/revoke`, `/oauth/introspect` using `application/x-www-form-urlencoded` |
| Unknown JSON field | Reject and return validation error |
| Maximum Request Body | 64 KiB |
| Time | JWT time field uses Unix timestamp (seconds) |
| Management API | `/v1/admin/*` is outside the public integration scope |

## 2. Headers

| Header | Scope | Required | Format and constraints |
|---|---|---|---|
| `Content-Type` | Payload requests | Required | General API: `application/json`; OAuth form endpoint: `application/x-www-form-urlencoded` |
| `Accept` | ALL | OPTIONAL | RECOMMEND `application/json` |
| `Accept-Language` | `/v1/*` | OPTIONAL | `zh-TW` OR `en`; OTHER VALUES RETURNED IN ENGLISH |
| `X-Session-Platform-Code` | `/v1/*` | Required | Operator-issued platform code/"realm slug” such as `topinkiwi` |
| `Authorization` | Bearer JWT, S2S API Key | By Endpoint | `Bearer <access_token>` or `Bearer <sk_API_KEY>` |
| `X-Request-Id` | All | Optional | 1—128 characters, only alphanumeric, `.`, `_`, `-`; valid values are returned in Response Header |

Note:

- `/realms/{slug}/*` `X-Session-Platform-Code` IS NOT REQUIRED.
- `/v1/*` requests must include `X-Session-Platform-Code` even when no authentication is required.
- The S2S API Key can only be placed in the backend Secret Management System, not in the browser, Mobile App, source code or Log.
- Error Response's `trace_id` corresponds to `X-Request-Id`, please provide it together when reporting problems.

## 3. Response and Error Formatting

### 3.1 `/v1` Success Format

Except for `204 No Content`, successful responses wrap their payload in `data`:

```json
{
  "data": {
    "example": true
  }
}
```

### 3.2 `/v1` Error Format

```json
{
  "error": {
    "code": "COMMON_VALIDATION_FAILED",
    "id": 1001,
    "message": "The request format or field is invalid",
    "trace_id": "5b5aa30b-00fd-46ab-a836-322c779ff2c8"
  }
}
```

Clients must branch on the stable `code` value; `message` is for display only. `429 COMMON_RATE_LIMITED` comes with the `Retry-After` Response Header. Clients must wait for the number of seconds in `Retry-After` and use exponential backoff.

### 3.3 OAuth Error Formatting

`/realms/{slug}/oauth/*` complies with OAuth JSON error and does not use `/v1` envelope:

```json
{
  "error": "invalid_grant",
  "error_description": "the authorization grant is invalid"
}
```

OAuth token and sensitive-data responses include `Cache-Control: no-store`, `Pragma: no-cache`.

## 4. OIDC Discovery and JWKS

### GET /realms/{slug}/.well-known/openid-configuration

Get Realm's OIDC metadata.

**Headers:** `Accept: application/json` (Optional)
**Path Parameters:** `slug`, Operator-issued Realm slug.
**Query Parameters:** None.
**Payload:** None.
**Authentication:** None.

```bash
curl https://identity.lifeintent.app/realms/topinkiwi/.well-known/openid-configuration
```

**Success:`200 OK`**

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

**Errors:** A missing or suspended Realm and an invalid slug all return the same `404 COMMON_NOT_FOUND` to avoid leaking Realm status.
**Security:** Use the returned endpoints as-is; do not construct or rewrite them as `/v1/realms/*`.

### GET /realms/{slug}/.well-known/jwks.json

Obtain the RS256 public seal key for the Realm.

**Headers:** `Accept: application/json` (Optional)
**Path Parameters:** `slug`.
**Query Parameters:** None.
**Payload:** None.
**Authentication:** None.

**Success:`200 OK`,`Cache-Control: public, max-age=300`**

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

**Errors:** Same as Discovery.
**Security:** JWKS contains public materials only; select the `kid` key in the JWT header when authenticating, and only `RS256` is accepted.

## 5. OAuth 2.0 Authorization Code + PKCE

All endpoints use `/realms/{slug}`, without `X-Session-Platform-Code`. Public clients do not have Client Secret and must use PKCE `S256`.

### POST /realms/{slug}/oauth/authorize

Create short-term, one-time license transactions.

**Headers**

| Name | Required | Value |
|---|---|---|
| `Content-Type` | YES | `application/json` |

**Path Parameters:** `slug`.
**Query Parameters:** None.

**Payload**

| Fields | Type | Required | Restrictions |
|---|---|---|---|
| `response_type` | string | Yes | Fixed `code` |
| `client_id` | string | Yes | Registered client ID of the operator |
| `redirect_uri` | string | Yes | Must Match with Register Value Exact |
| `scope` | string | Yes | Blank delimited; allowed scope must be included |
| `state` | string | Yes | Client-generated high entropy random value |
| `nonce` | string | Yes | Client generated, then used to validate the ID Token |
| `code_challenge` | string | Yes | `BASE64URL(SHA256(code_verifier))` |
| `code_challenge_method` | string | Yes | Fixed `S256` |

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

**Success:`200 OK`**

```json
{
  "transaction": "txn_opaque_value",
  "expires_in": 300
}
```

**Errors:** `invalid_request`, `unauthorized_client`, `invalid_scope`; A missing or suspended Realm returns the same `404 invalid_request`.
**Security:** `state`, `nonce`, `code_verifier` must be generated by CSPRNG; passwords or transaction handles must not be recorded.

### POST /realms/{slug}/oauth/authorize/login

Authorize transactions confidentially; if the account has MFA enabled, return to the MFA challenge.

**Headers:** `Content-Type: application/json`
**Path Parameters:** `slug`.
**Query Parameters:** None.

**Payload**

| Fields | Type | Required | Help |
|---|---|---|---|
| `transaction` | string | Yes | authorize return one-time transaction handle |
| `tenant` | string | Yes | Tenantless Airspace String |
| `username` | string | Yes | User Account |
| `password` | string | Yes | User Password |

```json
{
  "transaction": "txn_opaque_value",
  "tenant": "",
  "username": "alice",
  "password": "S3cure-Pass!"
}
```

**Success A:`200 OK`,No MFA**

```json
{
  "code": "authorization-code",
  "state": "random-state",
  "redirect_uri": "https://app.example.com/callback"
}
```

**Success B:`200 OK`, requires MFA**

```json
{
  "mfa_required": true,
  "mfa_token": "mfa_opaque_value"
}
```

**Errors:** `invalid_grant`, `access_denied`, `invalid_transaction`.
**Security:** The client must match `state` after receiving the result, the authorization code is short-lived and single-use.

### POST /realms/{slug}/oauth/authorize/mfa

Complete an authorized transaction with TOTP using the MFA challenge.

**Headers:** `Content-Type: application/json`
**Path Parameters:** `slug`.
**Query Parameters:** None.

**Payload**

```json
{
  "transaction": "txn_opaque_value",
  "mfa_token": "mfa_opaque_value",
  "code": "123456"
}
```

All three fields are required strings; `code` is the current 6-digit number of the validator.

**Success:`200 OK`**

```json
{
  "code": "authorization-code",
  "state": "random-state",
  "redirect_uri": "https://app.example.com/callback"
}
```

**Errors:** `invalid_grant`, `invalid_transaction`, `access_denied`.
**Security:** `transaction`, `mfa_token` and TOTP challenge are short-lived and one-time.

### POST /realms/{slug}/oauth/token

Get Tokens with Authorization Code+PKCE or Refresh Token.

**Headers:** `Content-Type: application/x-www-form-urlencoded`
**Path Parameters:** `slug`.
**Query Parameters:** None.
**Authentication:** Public clients do not use Client Secret.

**Authorization Code Payload**

| Field | Required | Value |
|---|---|---|
| `grant_type` | YES | `authorization_code` |
| `code` | YES | ONE-TIME AUTHORIZATION CODE OBTAINED IN THE PREVIOUS STEP |
| `redirect_uri` | Yes | Must be exactly the same as authorize |
| `client_id` | Yes | Registered client ID |
| `code_verifier` | Yes | PKCE verifier corresponding to original `code_challenge` |

```bash
curl -X POST https://identity.lifeintent.app/realms/topinkiwi/oauth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=authorization_code" \
  -d "code=authorization-code" \
  -d "redirect_uri=https://app.example.com/callback" \
  -d "client_id=topinkiwi-web" \
  -d "code_verifier=original-verifier"
```

**Success:`200 OK`**

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

| Field | Required | Value |
|---|---|---|
| `grant_type` | YES | `refresh_token` |
| `refresh_token` | Yes | Recently Obtained OAuth Refresh Token |
| `client_id` | Yes | Original client ID |

Refresh successfully refreshed `access_token`, `refresh_token`, `token_type`, `expires_in`, `scope`, and did not restore `id_token`.

**Errors:** `invalid_request`, `invalid_client`, `invalid_grant`, `unsupported_grant_type`.
**Security:** The Refresh Token rotates after every use; only the newest token may be retained. Authorization Code cannot be reused after authentication fails.

### POST /realms/{slug}/oauth/revoke

Revoke the Access or Refresh Token in accordance with RFC 7009.

**Headers:** `Content-Type: application/x-www-form-urlencoded`
**Path Parameters:** `slug`.
**Query Parameters:** None.

**Payload**

| Fields | Required | Help |
|---|---|---|
| `token` | Yes | Tokens to be withdrawn |
| `client_id` | Yes | Token belongs to client |

**Success:`200 OK`**

```json
{}
```

Whether tokens exist returns the same success result.
**Errors:** A missing or disabled client returns `401 invalid_client`; format error returns `invalid_request`.
**Security:** Cannot infer whether a Token existed by Response.

### POST /realms/{slug}/oauth/introspect

Resource Server queries Token status with S2S API Key in accordance with RFC 7662.

**Headers**

| Name | Required | Value |
|---|---|---|
| `Authorization` | YES | `Bearer <sk_API_KEY>` |
| `Content-Type` | YES | `application/x-www-form-urlencoded` |

**Path Parameters:** `slug`.
**Query Parameters:** None.
**Payload:** `token=<access_or_refresh_token>`.

**Inactive:`200 OK`**

```json
{"active": false}
```

**Active:`200 OK`**

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

**Errors:** Missing, incorrect, or cross-Realm API Key always returns the same `401 invalid_client`.
**Security:** General requests prioritize local JWKS validation; Introspection is only required when instant revocation status is required.

## 6. Login and Session

All `/v1/*` endpoints in this chapter must carry `X-Session-Platform-Code`.

### POST /v1/auth/login

**Headers:** `X-Session-Platform-Code`, `Content-Type: application/json`
**Path Parameters:** None.
**Query Parameters:** None.

**Payload**

| Fields | Type | Required | Help |
|---|---|---|---|
| `username` | string | Yes | Account |
| `password` | string | Yes | Password |
| `tenant` | string | Yes | Tenantless Timeline `""` |

```json
{"username":"alice","password":"S3cure-Pass!","tenant":""}
```

**Success A:`200 OK`**

```json
{"data":{"access_token":"eyJ...","refresh_token":"rt_...","expires_in":2700}}
```

**Success B:`200 OK`**

```json
{"data":{"mfa_required":true,"mfa_token":"mfa_..."}}
```

**Errors:** `AUTH_INVALID_CREDENTIALS`, `AUTH_ACCOUNT_DISABLED`, `AUTH_ACCOUNT_LOCKED`, `COMMON_VALIDATION_FAILED`, `AUTH_PLATFORM_UNKNOWN`, `COMMON_RATE_LIMITED`.
**Security:** Response with `Cache-Control: no-store`; account non-existence is indistinguishable from password errors.

### POST /v1/auth/refresh

**Headers:** `X-Session-Platform-Code`, `Content-Type: application/json`
**Path/Query Parameters:** None.

**Payload**

```json
{"refresh_token":"rt_..."}
```

**Success:`200 OK`**

```json
{"data":{"access_token":"eyJ...","refresh_token":"rt_new...","expires_in":2700}}
```

**Errors:** `AUTH_REFRESH_INVALID`, `AUTH_REFRESH_REUSED`, `COMMON_VALIDATION_FAILED`.
**Security:** Refresh Token rotates immediately each time it is reissued; reusing old tokens will revoke all Refresh Tokens in that account.

### POST /v1/auth/logout

**Headers:** `X-Session-Platform-Code`, `Content-Type: application/json`
**Path/Query Parameters:** None.
**Payload:** `{"refresh_token":"rt_..."}`.
**Success:`204 No Content`,No Response body.
**Errors:** `COMMON_VALIDATION_FAILED` when payload is invalid.
**Security:** Valid or non-existent Tokens should not cause recognizable differences.

### GET /v1/.well-known/jwks.json

Obtain the public seal key for the platform profile.

**Headers:** `X-Session-Platform-Code`
**Path/Query Parameters:** None.
**Payload:** None.
**Success:** `200 OK`, formatted as Realm JWKS,`Cache-Control: public, max-age=300`.
**Errors:** `AUTH_PLATFORM_UNKNOWN`, `COMMON_INTERNAL_ERROR`.
**Security:** `/v1` Access Token authentication requires checking both RS256 signature, `iss`, `aud`, `exp` and allowed `typ`.

## 7. MFA

### POST /v1/auth/mfa/verify

**Headers:** `X-Session-Platform-Code`, `Content-Type: application/json`
**Payload:** `{"mfa_token":"mfa_...","code":"123456"}`.
**Path/Query Parameters:** None.
**Success:** `200 OK`, returns TokenResponse.
**Errors:** `AUTH_MFA_INVALID_CODE`, `COMMON_VALIDATION_FAILED`.
**Security:** `mfa_token` 5 minutes, one-time; authentication failure will also consume.

### POST /v1/auth/mfa/recovery

**Headers:** `X-Session-Platform-Code`, `Content-Type: application/json`
**Payload:** `{"mfa_token":"mfa_...","recovery_code":"XXXXX-XXXXX"}`.
**Path/Query Parameters:** None.
**Success:** `200 OK`, returns TokenResponse.
**Errors:** `AUTH_RECOVERY_CODE_INVALID`, `AUTH_MFA_INVALID_CODE`, `COMMON_VALIDATION_FAILED`.
**Security:** A recovery code becomes invalid immediately after use.

### POST /v1/auth/mfa/setup

**Headers:** `X-Session-Platform-Code`, `Authorization: Bearer <access_token>`
**Content-Type./Payload:** None.
**Path/Query Parameters:** None.

**Success:`200 OK`**

```json
{"data":{"secret":"BASE32SECRET","otpauth_uri":"otpauth://totp/..."}}
```

**Errors:** `AUTH_TOKEN_INVALID`, `AUTH_TOKEN_EXPIRED`, `AUTH_TOKEN_REVOKED`, `AUTH_MFA_ALREADY_ENABLED`.
**Security:** `secret` is only used for the binding screen at the same time, no Log is allowed to be written.

### POST /v1/auth/mfa/activate

**Headers:** `X-Session-Platform-Code`, `Authorization: Bearer <access_token>`, `Content-Type: application/json`
**Payload:** `{"code":"123456"}`.
**Path/Query Parameters:** None.

**Success:`200 OK`**

```json
{"data":{"enabled":true,"recovery_codes":["XXXXX-XXXXX","...10 total"]}}
```

**Errors:** `AUTH_MFA_INVALID_CODE`, `AUTH_TOKEN_INVALID`, `COMMON_VALIDATION_FAILED`.
**Security:** Recovery Codes are returned only once, and the Client must deliver the user's secure save immediately.

### POST /v1/auth/mfa/disable

**Headers:** `X-Session-Platform-Code`, `Authorization: Bearer <access_token>`, `Content-Type: application/json`
**Payload:** `{"password":"current-password","code":"123456"}`.
**Path/Query Parameters:** None.
**Success:** `200 OK`,`{"data":{"enabled":false}}`.
**Errors:** `AUTH_INVALID_CREDENTIALS`, `AUTH_MFA_INVALID_CODE`, `AUTH_TOKEN_INVALID`.
**Security:** Disabling will void existing Recovery Codes.

### POST /v1/auth/mfa/recovery-codes/regenerate

**Headers:** `X-Session-Platform-Code`, `Authorization: Bearer <access_token>`, `Content-Type: application/json`
**Payload:** `{"password":"current-password","code":"123456"}`.
**Path/Query Parameters:** None.

**Success:`200 OK`**

```json
{"data":{"recovery_codes":["XXXXX-XXXXX","...10 total"]}}
```

**Errors:** `AUTH_INVALID_CREDENTIALS`, `AUTH_MFA_INVALID_CODE`, `AUTH_TOKEN_INVALID`.
**Security:** All previous recovery codes become invalid; new codes are returned in plaintext only once.

## 8. Registration, Email, Password and High Privilege Account Recovery

### POST /v1/auth/register

**Headers:** `X-Session-Platform-Code`, `Content-Type: application/json`
**Payload:** `{"email":"alice@example.com","password":"correct-horse-battery"}`.
**Path/Query Parameters:** None.

**Success:`202 Accepted`**

```json
{"data":{"accepted":true}}
```

**Errors:** Email/password format or Realm does not allow self-registration as `COMMON_VALIDATION_FAILED`; a password found in a known breach is `AUTH_PASSWORD_COMPROMISED`; shared quota exhaustion is `COMMON_RATE_LIMITED`.
**Security:** A successful registration and an equivalent existing email in the same Realm return exactly the same status and body. Passwords must be between 12 and 128 Unicode characters; Account, Credential, Primary Email are created in the same transaction as Required Action. Self-registration is allowed only for member Realms that require email verification, allow pending accounts, and do not require MFA for activation; `system` Realm always refuses. If email delivery temporarily fails after registration, the resend endpoint can be called safely. All Lambda Runtimes share PostgreSQL dual-layer restrictions: by default, 5 attempts per Realm/IP every 10 minutes and 100 attempts per Realm every minute; only an HMAC of the source IP is stored.

### POST /v1/auth/email/verify/request

**Headers:** `X-Session-Platform-Code`, `Content-Type: application/json`
**Payload:** `{"email":"alice@example.com"}`.
**Path/Query Parameters:** None.
**Success:** `202 Accepted`,`{"data":{"accepted":true}}`.
**Errors:** An empty or invalid payload is `COMMON_VALIDATION_FAILED`.
**Security:** Generic Response; The response does not reveal whether the email exists, is verified, was account-level rate-limited, or was delivered successfully. For the same account and purpose, the defaults are a 1-minute cooldown, 5 messages per hour, and 10 messages per 24 hours. A successful resend immediately invalidates the previous token.

### POST /v1/auth/email/verify/confirm

**Headers:** `X-Session-Platform-Code`, `Content-Type: application/json`
**Payload:** `{"token":"evt_opaque_value"}`.
**Path/Query Parameters:** None.
**Success:** `200 OK`,`{"data":{"verified":true}}`.
**Errors:** `AUTH_RECOVERY_TOKEN_INVALID`, `COMMON_VALIDATION_FAILED`.
**Security:** Tokens are short-lived, one-time, and Realm-bound, and cannot be reused after completion. If `verify_email` is the last Required Action, Email, Action, and Account are updated in the same transaction.

### POST /v1/auth/password/reset/request

**Headers:** `X-Session-Platform-Code`, `Content-Type: application/json`
**Payload:** `{"email":"alice@example.com"}`.
**Path/Query Parameters:** None.
**Success:** `202 Accepted`,`{"data":{"accepted":true}}`.
**Errors:** An empty or invalid payload is `COMMON_VALIDATION_FAILED`.
**Security:** Generic Response, avoids account enumeration; uses the same atomic account-level rate-limit policy as verification email, but counts independently for `password_reset` purposes. The old Token will expire immediately upon successful resend.

### POST /v1/auth/password/reset/confirm

**Headers:** `X-Session-Platform-Code`, `Content-Type: application/json`
**Payload:** `{"token":"pr_opaque_value","new_password":"new-secure-password"}`.
**Path/Query Parameters:** None.
**Success:** `200 OK`,`{"data":{"reset":true}}`.
**Errors:** `AUTH_RECOVERY_TOKEN_INVALID`, `AUTH_PASSWORD_COMPROMISED`, `COMMON_VALIDATION_FAILED`.
**Security:** Revoke the existing Refresh Token for the account after success; the new password must not appear in the known-breach list.

### POST /v1/auth/privileged-recovery/request

**Headers:** `X-Session-Platform-Code`, `Content-Type: application/json`
**Payload:** `{"tenant":"","username":"staff-user"}`.
**Path/Query Parameters:** None.
**Success:** `200 OK`,`{"data":{}}`.
**Errors:** Invalid payload for `COMMON_VALIDATION_FAILED`.
**Security:** Generic Response; the response does not reveal whether the account exists or is privileged. Only high-privilege accounts with a verified primary email create requests and send tokens; this endpoint is not mounted when Email Sender is not configured.

### POST /v1/auth/privileged-recovery/complete

Complete high-privilege account MFA recovery with Email Token plus existing Recovery Code.

**Headers:** `X-Session-Platform-Code`, `Content-Type: application/json`
**Payload:** `{"token":"pvr_opaque_value","recovery_code":"XXXXX-XXXXX"}`.
**Path/Query Parameters:** None.
**Success:** `200 OK`,`{"data":{}}`.
**Errors:** `AUTH_PRIVILEGED_RECOVERY_INVALID`, `COMMON_VALIDATION_FAILED`.
**Security:** Token and Recovery Code must be valid; any failure converges to the same error, avoiding side channels.

### POST /v1/auth/privileged-recovery/complete-with-approval

Complete the recovery with Email Token plus the operator's approved status.

**Headers:** `X-Session-Platform-Code`, `Content-Type: application/json`
**Payload:** `{"token":"pvr_opaque_value"}`.
**Path/Query Parameters:** None.
**Success:** `200 OK`,`{"data":{}}`.
**Errors:** `AUTH_PRIVILEGED_RECOVERY_INVALID`, `COMMON_VALIDATION_FAILED`.
**Security:** Unapproved, expired, used, or incorrect tokens return the same error.

## 9. S2S Account Provisioning

The S2S endpoint can only be called from the platform backend. Each request must include the platform code and the API Key for that Realm.

### POST /v1/internal/accounts

**Headers**

| Name | Required | Value |
|---|---|---|
| `X-Session-Platform-Code` | YES | `<platform_code>` |
| `Authorization` | YES | `Bearer <sk_API_KEY>` |
| `Content-Type` | YES | `application/json` |

**Path/Query Parameters:** None.

**Payload**

| Fields | Type | Required | Help |
|---|---|---|---|
| `tenant` | string | Yes | Tenantless Timeline `""` |
| `type` | string | Yes | `member` or `staff` |
| `username` | string | Yes | In-Platform Account Name |
| `password` | string | Yes | Initial password, up to 1024 characters |

```json
{"tenant":"","type":"member","username":"alice","password":"S3cure-Pass!"}
```

**Success:`201 Created`**

```json
{"data":{"sub":"acc_01..."}}
```

**Errors:** `AUTH_TOKEN_INVALID`, `AUTH_PLATFORM_UNKNOWN`, `COMMON_IDEMPOTENCY_CONFLICT`, `COMMON_VALIDATION_FAILED`.
**Security:** `sub` is a stable identifier for access-linked business data; plaintext passwords must not be stored. Cross-Realm API Key use is always rejected.

### PATCH /v1/internal/accounts/{sub}

Perform deactivation/activation, password reset, or emergency revocation for your account, with only one option available.

**Headers:** Provide endpoints with the same account.
**Path Parameters:** Identification of accounts starting with `sub`, `acc_`.
**Query Parameters:** None.

**Payload, Three Choices and One**

```json
{"status":"disabled"}
```

```json
{"reset_password":"new-secure-password"}
```

```json
{"revoke_all":true}
```

`status` ONLY ACCEPTS `active` OR `disabled`.

**Success:`200 OK`**

```json
{"data":{"sub":"acc_01...","applied":true}}
```

**Errors:** `COMMON_NOT_FOUND`, `COMMON_VALIDATION_FAILED`, `AUTH_TOKEN_INVALID`.
**Security:** Disabling the account revokes the Refresh Token; `revoke_all` is used for emergency response to suspicious account theft.

## 10. Health Check

### GET /livez

**Headers‧ Path‧ Query‧ Payload:** None.
**Authentication:** None.
**Success:** `200 OK`,`{"status":"live"}`.
**Purpose:** Process survival check, does not mean the database is ready.

### GET /readyz

**Headers‧ Path‧ Query‧ Payload:** None.
**Authentication:** None.
**Success:** `200 OK`,`{"status":"ready"}`.
**Not Ready:** `503 Service Unavailable`,`{"status":"not_ready"}`.
**Purpose:** Verify that service dependencies are available.

## 11. Token and Security Requirements

| Certificates | Forms | Core Specifications |
|---|---|---|
| `/v1` Access Token | RS256 JWT | Local JWKS Validation; `iss`, `aud`, `exp`, `typ` |
| `/v1` Refresh Token | `rt_...` Opaque Value | Alternate; Reuse Triggers Full Account Revocation |
| OAuth Access Token | `typ=at+jwt` RS256 JWT | Realm issuer; Default Short-Term |
| OAuth ID Token | RS256 JWT | Validate `aud == client_id`, `nonce`, `iss`, `exp` |
| OAuth Refresh Token | Selector + Secret Opaque Value | Bind client and session, alternating each time use |
| Authorization Code | Opaque value | Short-term, one-time, binding redirect URI to PKCE |
| `mfa_token` | `mfa_...` | 5 MINUTES, ONE-TIME |
| Recovery Code | `XXXXX-XXXXX` | Disposable, only displayed when generated |
| S2S API Key | `sk_...` | Backend save only, Realm-scoped |

Clients must:

1. ACCEPT ONLY `RS256`, REJECTING `alg=none`, HMAC CONFUSION AND UNKNOWN ALGORITHMS.
2. Verify token issuer, audience, expiry, type, and required nonce.
3. Do not write Password, Token, API Key, MFA Secret, Recovery Code to Log.
4th. AVOID `429` BY `Retry-After`; DO NOT AUTOMATICALLY RETRY FOR NORMAL `4xx`.
5. The OAuth Redirect URI takes Exact Match and does not self-regularize trailing slashes.
6th. Access Token prioritizes memory; if cookies are used, `HttpOnly`, `Secure` and the appropriate `SameSite` must be used.

## 12. Error code

| id | code | HTTP | Help |
|---: |---|---: |---|
| 1000 | `COMMON_INTERNAL_ERROR` | 500 | INTERNAL ERROR REPORTED WITH `trace_id` |
| 1001 | `COMMON_VALIDATION_FAILED` | 422 | JSON, FIELD, TYPE, OR CONSTRAINT MISMATCH |
| 1002 | `COMMON_NOT_FOUND` | 404 | RESOURCE OR PATH DOES NOT EXIST |
| 1003 | `COMMON_RATE_LIMITED` | 429 | Retry after the number of seconds specified by `Retry-After` |
| 1004 | `COMMON_IDEMPOTENCY_CONFLICT` | 409 | UNIQUE RESOURCE EXISTS |
| 1005 | `COMMON_FORBIDDEN` | 403 | VERIFIED BUT NOT PRIVILEGED |
| 2001 | `AUTH_INVALID_CREDENTIALS` | 401 | ACCOUNT OR PASSWORD ERROR |
| 2002 | `AUTH_ACCOUNT_DISABLED` | 403 | ACCOUNT DEACTIVATED |
| 2003 | `AUTH_ACCOUNT_LOCKED` | 423 | TEMPORARILY LOCKED AFTER MULTIPLE LOGIN FAILURES |
| 2004 | `AUTH_MFA_REQUIRED` | 401 | PROCESS REQUIRES MFA |
| 2005 | `AUTH_MFA_INVALID_CODE` | 401 | INVALID TOTP or challenge |
| 2006 | `AUTH_MFA_ALREADY_ENABLED` | 409 | MFA ENABLED |
| 2007 | `AUTH_RECOVERY_CODE_INVALID` | 401 | Recovery Code invalid or used |
| 2008 | `AUTH_REFRESH_INVALID` | 401 | Refresh Token Invalid or Expired |
| 2009 | `AUTH_REFRESH_REUSED` | 401 | Refresh Token Reuse Detected |
| 2010 | `AUTH_TOKEN_EXPIRED` | 401 | Access Token Expired |
| 2011 | `AUTH_TOKEN_INVALID` | 401 | Invalid JWT, API Key or Bearer format |
| 2012 | `AUTH_TOKEN_REVOKED` | 401 | Token Urgent Withdrawal |
| 2013 | `AUTH_PLATFORM_UNKNOWN` | 400 | Platform code unresolvable, unknown or disabled |
| 2014 | `AUTH_RECOVERY_TOKEN_INVALID` | 401 | Email/Password Recovery Token Invalid, Expired or Used |
| 2015 | `AUTH_PASSWORD_COMPROMISED` | 422 | PASSWORD EXISTS IN KNOWN LEAK LIST |
| 2016 | `AUTH_MFA_SETUP_REQUIRED` | 403 | PRIVILEGE PROCESS HAS NOT COMPLETED MFA SETUP |
| 2017 | `AUTH_PRIVILEGED_RECOVERY_INVALID` | 401 | PRIVILEGE MFA RECOVERY REQUEST INVALID |

## 13. Minimum Integration Checklist

```bash
# Liveness
curl https://identity.lifeintent.app/livez

# Realm Discovery
curl https://identity.lifeintent.app/realms/<slug>/.well-known/openid-configuration

# /v1 JWKS
curl https://identity.lifeintent.app/v1/.well-known/jwks.json \
  -H "X-Session-Platform-Code: <platform_code>"
```

If the above request is successful, then choose according to the use case:

- Standard third party login: OAuth Authorization Code+PKCE.
- CONFIDENTIAL LOGIN FROM YOUR PLATFORM: `POST /v1/auth/login`.
- BACKEND ACCOUNT AVAILABLE: `POST /v1/internal/accounts`.

See also `INTEGRATION.md` for the complete end-to-end process.
