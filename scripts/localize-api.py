#!/usr/bin/env python3
"""由繁體中文 API.md 產生簡體中文與英文 Markdown。

簡體中文使用 OpenCC 做字詞轉換；英文使用 Amazon Translate。翻譯前會保護
Code Fence、Inline Code 與端點標題，避免 API path、JSON 與程式識別字被翻譯。
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import tempfile
from pathlib import Path

from opencc import OpenCC

ROOT = Path(__file__).resolve().parent.parent

DOCUMENTS = {
    "api": ("API.md", "API.zh-Hans.md", "API.en.md"),
}


def protect_markdown(source: str) -> tuple[str, list[str]]:
    protected: list[str] = []
    pattern = re.compile(
        r"```.*?```|`[^`\n]+`|(?<=^### )(?:GET|POST|PATCH) /\S+",
        re.DOTALL | re.MULTILINE,
    )

    def replace(match: re.Match[str]) -> str:
        token = f"ZXQPROTECT{len(protected):05d}QXZ"
        protected.append(match.group(0))
        return token

    return pattern.sub(replace, source), protected


def restore_markdown(translated: str, protected: list[str]) -> str:
    for index, value in enumerate(protected):
        token = f"ZXQPROTECT{index:05d}QXZ"
        if token not in translated:
            raise RuntimeError(f"Amazon Translate 未保留保護標記：{token}")
        translated = translated.replace(token, value)
    if "ZXQPROTECT" in translated:
        raise RuntimeError("翻譯結果仍含未知保護標記")
    return translated


def normalize_english(source: str) -> str:
    source = source.translate(
        str.maketrans({"：": ":", "，": ",", "。": ".", "、": ", ", "；": ";", "／": "/"})
    )
    source = re.sub(r"\*\*([^*\n]+?): \*\*", r"**\1:**", source)
    source = re.sub(r"^> Base URL:\s*", "> Base URL: ", source, flags=re.MULTILINE)
    replacements = {
        "# Identity Service Public API File": "# Identity Service Public API Documentation",
        "> File Update:": "> Last updated:",
        "> The public domain does not include operator-specific": "> The public scope excludes operator-only",
        "## 1. Common Provisions": "## 1. Common Conventions",
        "|Projects|Specifications|": "| Item | Requirement |",
        "| Header | Scope | Necessity | Formats and Restrictions |": "| Header | Scope | Required | Format and constraints |",
        "- `/v1/*`: PLATFORM LOGIN, ACCOUNT SELF-SERVICE, MFA AND S2S ACCOUNT SUPPLY, EACH REQUEST MUST INCLUDE": "- `/v1/*`: platform login, account self-service, MFA, and S2S account provisioning. Every request must include",
        "| TLS | ALL ENDPOINTS USE HTTPS ONLY |": "| TLS | All endpoints use HTTPS only |",
        "| MANAGEMENT API |": "| Management API |",
        "| `/v1/admin/*` DOES NOT BELONG TO PUBLIC SERIAL SCOPE |": "| `/v1/admin/*` is outside the public integration scope |",
        "### 3.1 `/v1` SUCCESSFUL FORMAT": "### 3.1 `/v1` Success Format",
        "### 3.2 `/v1` ERROR FORMAT": "### 3.2 `/v1` Error Format",
        "In addition to `204 No Content`, the successful package in `data`:": "Except for `204 No Content`, successful responses wrap their payload in `data`:",
        "The program determines to use the stable string `code`; `message` is for display only.": "Clients must branch on the stable `code` value; `message` is for display only.",
        "Clients should wait in seconds and avoid using indices.": "Clients must wait for the number of seconds in `Retry-After` and use exponential backoff.",
        "OAuth Token and sensitive data response with": "OAuth token and sensitive-data responses include",
        "## 4. OIDC Discovery vs JWKS": "## 4. OIDC Discovery and JWKS",
        "**Certification:**": "**Authentication:**",
        "**Errori:**": "**Errors:**",
        "slug format is illegal": "slug is invalid",
        "Realm does not exist, suspend or slug is invalid to return the same": "A missing or suspended Realm and an invalid slug all return the same",
        "Based on the returned endpoint, do not self-spliced or changed to": "Use the returned endpoints as-is; do not construct or rewrite them as",
        "then authenticated ID Token": "then used to validate the ID Token",
        "Realm does not exist or has the right to suspend the indistinguishable": "A missing or suspended Realm returns the same",
        "the license code is short-lived and one-time": "the authorization code is short-lived and single-use",
        "ONE-TIME LICENSE CODE OBTAINED IN PREVIOUS STEP": "ONE-TIME AUTHORIZATION CODE OBTAINED IN THE PREVIOUS STEP",
        "Refresh Token rotates after each use; only the latest card can be kept.": "The Refresh Token rotates after every use; only the newest token may be retained.",
        "Client does not exist or has disabled the right to return": "A missing or disabled client returns",
        "## 7. M.F.A.": "## 7. MFA",
        "`/v1/*` MUST CARRY `X-Session-Platform-Code` EVEN WITHOUT CERTIFICATION.": "`/v1/*` requests must include `X-Session-Platform-Code` even when no authentication is required.",
        "Backup code will expire immediately after use.": "A recovery code becomes invalid immediately after use.",
        "The old Recovery Codes are all invalid; the new Codes are returned only once explicitly.": "All previous recovery codes become invalid; new codes are returned in plaintext only once.",
        "Successful Realm-equivalent Emails already exist in exactly the same state as Body.": "A successful registration and an equivalent existing email in the same Realm return exactly the same status and body.",
        "known leak password": "a password found in a known breach",
        "share quota exceeded": "shared quota exhaustion",
        "Only member Realm that requires Email authentication, allows pending, and does not require MFA to be enabled;": "Self-registration is allowed only for member Realms that require email verification, allow pending accounts, and do not require MFA for activation;",
        "Securely call resend endpoint compensation can be invoked in case of temporary failure after registration.": "If email delivery temporarily fails after registration, the resend endpoint can be called safely.",
        "5 times per 10 minutes with Realm/IP default, 100 times per minute for a single Realm; HMAC for ground IP only.": "by default, 5 attempts per Realm/IP every 10 minutes and 100 attempts per Realm every minute; only an HMAC of the source IP is stored.",
        "Empty or illegal Payload": "An empty or invalid payload",
        "Whether an email exists, is authenticated, streamed at the account level, or sent successfully is not determined by Response.": "The response does not reveal whether the email exists, is verified, was account-level rate-limited, or was delivered successfully.",
        "The same-account, same-use limit is set to 1 minute cooldown, 5 times per hour, 10 times 24 hours; old tokens expire immediately upon successful resend.": "For the same account and purpose, the defaults are a 1-minute cooldown, 5 messages per hour, and 10 messages per 24 hours. A successful resend immediately invalidates the previous token.",
        "enabled in the same Transaction location.": "updated in the same transaction.",
        "shares account-level atomic limit flow policy with authentication": "uses the same atomic account-level rate-limit policy as verification email",
        "does not appear in the list of known leaks": "does not appear in the known-breach list",
        "must not appear in the list of known leaks": "must not appear in the known-breach list",
        "whether an account exists or is not recognized as a high-privilege account.": "the response does not reveal whether the account exists or is privileged.",
        "authenticated Primary Email": "a verified primary email",
        "## 9. S2S Account Supply": "## 9. S2S Account Provisioning",
        "text passwords cannot be stored": "plaintext passwords must not be stored",
        "API Key usage is always denied across Realm.": "Cross-Realm API Key use is always rejected.",
        "## 11. Token and Security Regulations": "## 11. Token and Security Requirements",
        "Please avoid using `Retry-After`": "Retry after the number of seconds specified by `Retry-After`",
        "## 13. Minimum serial check": "## 13. Minimum Integration Checklist",
        '"message": "請求格式或欄位無效"': '"message": "The request format or field is invalid"',
        '"...共 10 組"': '"...10 total"',
        "# 存活": "# Liveness",
    }
    for original, corrected in replacements.items():
        source = source.replace(original, corrected)
    return source


def translate_english(source: str, region: str) -> str:
    protected_source, protected = protect_markdown(source)
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8") as handle:
        handle.write(protected_source)
        handle.flush()
        try:
            completed = subprocess.run(
                [
                    "aws",
                    "translate",
                    "translate-document",
                    "--region",
                    region,
                    "--source-language-code",
                    "zh-TW",
                    "--target-language-code",
                    "en",
                    "--document-content",
                    f"fileb://{handle.name}",
                    "--document",
                    "ContentType=text/plain",
                    "--output",
                    "json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as error:
            raise RuntimeError(error.stderr.strip() or "Amazon Translate 呼叫失敗") from error
    response = json.loads(completed.stdout)
    translated = base64.b64decode(response["TranslatedDocument"]["Content"]).decode("utf-8")
    return normalize_english(restore_markdown(translated, protected))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--skip-english", action="store_true")
    parser.add_argument("--normalize-existing-english", action="store_true")
    parser.add_argument("--only", choices=("all", *DOCUMENTS), default="all")
    args = parser.parse_args()

    selected = DOCUMENTS.items() if args.only == "all" else ((args.only, DOCUMENTS[args.only]),)
    for _, (source_name, simplified_name, english_name) in selected:
        source = (ROOT / source_name).read_text(encoding="utf-8")
        (ROOT / simplified_name).write_text(OpenCC("t2s").convert(source), encoding="utf-8")
        english = ROOT / english_name
        if args.normalize_existing_english:
            english.write_text(normalize_english(english.read_text(encoding="utf-8")), encoding="utf-8")
        elif not args.skip_english:
            english.write_text(translate_english(source, args.region), encoding="utf-8")


if __name__ == "__main__":
    main()
