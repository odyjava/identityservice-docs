#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

for file in index.html INTEGRATION.md API.md api.html; do
  test -f "$file" || {
    echo "缺少必要文件：$file" >&2
    exit 1
  }
done

required_paths='
GET /livez
GET /readyz
GET /realms/{slug}/.well-known/openid-configuration
GET /realms/{slug}/.well-known/jwks.json
POST /realms/{slug}/oauth/authorize
POST /realms/{slug}/oauth/authorize/login
POST /realms/{slug}/oauth/authorize/mfa
POST /realms/{slug}/oauth/token
POST /realms/{slug}/oauth/revoke
POST /realms/{slug}/oauth/introspect
POST /v1/auth/login
POST /v1/auth/refresh
POST /v1/auth/logout
GET /v1/.well-known/jwks.json
POST /v1/auth/mfa/verify
POST /v1/auth/mfa/recovery
POST /v1/auth/mfa/setup
POST /v1/auth/mfa/activate
POST /v1/auth/mfa/disable
POST /v1/auth/mfa/recovery-codes/regenerate
POST /v1/auth/register
POST /v1/auth/email/verify/request
POST /v1/auth/email/verify/confirm
POST /v1/auth/password/reset/request
POST /v1/auth/password/reset/confirm
POST /v1/auth/privileged-recovery/request
POST /v1/auth/privileged-recovery/complete
POST /v1/auth/privileged-recovery/complete-with-approval
POST /v1/internal/accounts
PATCH /v1/internal/accounts/{sub}
'

for spec in API.md api.html; do
  printf '%s\n' "$required_paths" | while IFS= read -r endpoint; do
    [ -z "$endpoint" ] && continue
    grep -Fq "$endpoint" "$spec" || {
      echo "$spec 缺少端點：$endpoint" >&2
      exit 1
    }
  done

  for term in \
    'https://identity.lifeintent.app' \
    'X-Session-Platform-Code' \
    'Authorization: Bearer' \
    'application/json' \
    'application/x-www-form-urlencoded' \
    'X-Request-Id' \
    'trace_id' \
    'COMMON_RATE_LIMITED' \
    'Retry-After'; do
    grep -Fq "$term" "$spec" || {
      echo "$spec 缺少必要規範：$term" >&2
      exit 1
    }
  done

  if grep -Fq '/v1/realms/{slug}/oauth' "$spec"; then
    echo "$spec 含已淘汰 OIDC 路徑" >&2
    exit 1
  fi

  if grep -Eq '536697232980|arn:aws:|RECOVERY_TOKEN_HASH_KEY=' "$spec"; then
    echo "$spec 疑似含基礎設施或 Secret 資訊" >&2
    exit 1
  fi
done

grep -Fq 'href="api.html"' index.html
grep -Fq 'href="API.md"' index.html
grep -Fq '2026-07-16' index.html
grep -Fq 'download' index.html
