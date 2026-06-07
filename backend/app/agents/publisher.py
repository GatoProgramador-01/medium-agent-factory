"""
PublisherAgent — human-in-the-loop Medium publishing
=====================================================

NOTE — Medium API status (researched June 2025)
------------------------------------------------
Medium's official REST API (api.medium.com) is DEPRECATED and archived.
- GitHub repo Medium/medium-api-docs archived 2023-03-02.
- Integration token generation removed for all new accounts as of 2025-01-01.
- Make.com confirmed (2024-12-25): "Medium has disabled their API. It only
  works if you created a token before that date."
- No working unofficial POST endpoint exists. The internal GraphQL endpoint
  (medium.com/_/graphql) is READ-ONLY; no write path has been documented.
- PyPI libraries: `medium-api` is read-only; `jupyter-to-medium` requires a
  token and is abandoned (Python <3.11 only).

Conclusion: Playwright browser automation is the ONLY reliable publish path
for any account that does not already hold a pre-2025 integration token.
Playwright has a first-class Python SDK (playwright.async_api) — this module
uses Python Playwright, not JavaScript.

Two paths (auto-selected by config):
  A. Medium API  — if MEDIUM_ACCESS_TOKEN is set in .env (legacy accounts only)
  B. Playwright  — headless Chromium with session saved to MongoDB (default)

Authentication (path B — one-time setup):
  1. POST /publisher/start-auth   {"email": "you@example.com"}
     Medium sends a magic-link email.
  2. Right-click the link in your email → Copy link address (DO NOT click it).
  3. POST /publisher/complete-auth {"magic_url": "https://medium.com/m/callback/..."}
     Playwright opens the URL headlessly, authenticates, saves session to MongoDB.
  Session persists across container restarts (stored in `publisher_sessions` col).

Human-in-the-loop visibility:
  Every Playwright action emits a log_step → pipeline/runs/{run_id}/logs.
  The frontend polls this endpoint and shows each step in the live terminal.

Selector strategy:
  Multiple CSS/aria fallback selectors per element (Medium changes UI often).
  If a selector list misses, the error message names all attempted selectors
  so they can be updated without reading this file.

Future optimisation notes:
  - Replace clipboard paste with Medium's internal GraphQL mutation if it
    ever becomes documented.
  - Consider BYOS (bring-your-own-session): let user paste their `sid` cookie
    directly into .env to skip the magic-link flow entirely.
  - The `grant_permissions(["clipboard-read","clipboard-write"])` call may
    need `--allow-clipboard` Chromium flag in certain Docker environments.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

import httpx
from playwright.async_api import Browser, BrowserContext, Page, async_playwright

from app.agents.logger import log_step
from app.config import settings
from app.database import get_db

# ── Constants ──────────────────────────────────────────────────────────────────

_SESSION_DOC_ID = "medium"
_SESSIONS_COL   = "publisher_sessions"

# Pending auth state shared across requests within the process
_pending_auth: dict[str, Any] = {}


# ── Title / body / tag selectors (tried in order) ─────────────────────────────

_TITLE_SELECTORS = [
    '[data-testid="titleParagraph"]',
    'h3.graf--title',
    '[aria-label="Title"]',
    'p.graf--title',
]

_BODY_SELECTORS = [
    '[data-testid="storyBody"] p',
    '[aria-label="Write…"]',
    '[aria-label="Write something"]',
    'p.graf--p',
]

_TAG_INPUT_SELECTORS = [
    '[placeholder*="Add a tag"]',
    '[placeholder*="tag"]',
    '[aria-label*="tag" i]',
]


# ── Session helpers ────────────────────────────────────────────────────────────

async def _load_session() -> dict | None:
    db = get_db()
    doc = await db[_SESSIONS_COL].find_one({"_id": _SESSION_DOC_ID})
    return doc.get("storage_state") if doc else None


async def _save_session(storage_state: dict) -> None:
    db = get_db()
    await db[_SESSIONS_COL].update_one(
        {"_id": _SESSION_DOC_ID},
        {"$set": {"storage_state": storage_state, "saved_at": datetime.now(UTC)}},
        upsert=True,
    )


# ── Auth flow — cookie-based (path B) ─────────────────────────────────────────
#
# Medium login only issues a one-time code sent to your email — no password.
# The easiest auth method is to copy the `sid` cookie from a browser where
# you are already logged in, then hand it to Playwright.
#
# How to find your sid cookie:
#   1. Open medium.com in Chrome/Firefox (logged in)
#   2. Press F12 → Application (Chrome) or Storage (Firefox)
#   3. Cookies → https://medium.com → find the row named "sid"
#   4. Copy the Value column
#
# Alternatively grab a full cookie JSON export via the browser extension
# "EditThisCookie" or "Cookie-Editor" → Export as JSON.

async def set_session_from_sid(sid: str) -> str:
    """
    Build a Playwright storage_state from a raw `sid` cookie value and
    verify it against medium.com before saving to MongoDB.
    """
    storage: dict = {
        "cookies": [
            {
                "name": "sid",
                "value": sid,
                "domain": ".medium.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            }
        ],
        "origins": [],
    }

    # Verify the session works before saving
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=storage)
        page    = await context.new_page()

        await page.goto("https://medium.com/me/stories/drafts", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        current = page.url
        if "signin" in current or "login" in current:
            await browser.close()
            raise RuntimeError(
                "Session verification failed — the sid cookie is expired or invalid. "
                "Copy a fresh sid from your browser DevTools and try again."
            )

        # Grab the full session state Medium set (may include additional cookies)
        full_storage = await context.storage_state()
        await browser.close()

    await _save_session(full_storage)
    return "Session verified and saved. Medium publishing is ready."


async def set_session_from_cookies_json(cookies_json: list[dict]) -> str:
    """
    Accept a full cookie JSON array (e.g. from Cookie-Editor browser extension)
    and build a Playwright session from it.  Verifies before saving.
    """
    # Normalise fields Playwright requires
    normalised = []
    for c in cookies_json:
        normalised.append({
            "name":     c.get("name", ""),
            "value":    c.get("value", ""),
            "domain":   c.get("domain", ".medium.com"),
            "path":     c.get("path", "/"),
            "httpOnly": c.get("httpOnly", False),
            "secure":   c.get("secure", False),
            "sameSite": c.get("sameSite", "Lax"),
        })

    storage: dict = {"cookies": normalised, "origins": []}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(storage_state=storage)
        page    = await context.new_page()

        await page.goto("https://medium.com/me/stories/drafts", wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        if "signin" in page.url or "login" in page.url:
            await browser.close()
            raise RuntimeError("Cookie verification failed — cookies may be expired.")

        full_storage = await context.storage_state()
        await browser.close()

    await _save_session(full_storage)
    return "Session verified and saved. Medium publishing is ready."


async def check_session_status() -> dict:
    """Return whether a saved session exists and if it's still valid."""
    session = await _load_session()
    if not session:
        return {"has_session": False, "valid": False}

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(storage_state=session)
            page    = await context.new_page()
            await page.goto("https://medium.com/me/stories/drafts",
                            wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)
            valid = "signin" not in page.url and "login" not in page.url
            await browser.close()
        return {"has_session": True, "valid": valid}
    except Exception as exc:
        return {"has_session": True, "valid": False, "error": str(exc)}


# ── Selector helper ────────────────────────────────────────────────────────────

async def _find(page: Page, selectors: list[str], description: str) -> Any:
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible():
                return loc
        except Exception:
            continue
    raise RuntimeError(
        f"Could not find {description}. "
        f"Tried: {selectors}. Medium may have changed their UI."
    )


# ── Medium API path ────────────────────────────────────────────────────────────

async def _publish_via_api(
    run_id: str,
    title: str,
    content: str,
    tags: list[str],
    publish_live: bool,
) -> str:
    token = settings.medium_access_token
    await log_step(run_id, "publisher", "Using Medium API token...")

    async with httpx.AsyncClient(timeout=30) as client:
        # Get user ID
        me = await client.get(
            "https://api.medium.com/v1/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        me.raise_for_status()
        user_id = me.json()["data"]["id"]
        await log_step(run_id, "publisher", f"Authenticated as user {user_id}")

        # Create post
        status = "public" if publish_live else "draft"
        resp = await client.post(
            f"https://api.medium.com/v1/users/{user_id}/posts",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "title": title,
                "contentFormat": "markdown",
                "content": content,
                "tags": tags[:5],
                "publishStatus": status,
            },
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        url: str = data.get("url", "")
        await log_step(
            run_id, "publisher",
            f"Post created via API — status: {status}, url: {url}",
            level="success",
            data={"url": url, "publish_status": status},
        )
        return url


# ── Playwright path ────────────────────────────────────────────────────────────

async def _publish_via_playwright(
    run_id: str,
    title: str,
    content: str,
    tags: list[str],
    publish_live: bool,
) -> str:

    session = await _load_session()
    if not session:
        raise RuntimeError(
            "No Medium session found. "
            "Run POST /publisher/start-auth first, then POST /publisher/complete-auth."
        )

    await log_step(run_id, "publisher", "Loading saved Medium session...")

    async with async_playwright() as pw:
        browser: Browser = await pw.chromium.launch(headless=True)
        context: BrowserContext = await browser.new_context(
            storage_state=session,
            viewport={"width": 1280, "height": 900},
        )
        page: Page = await context.new_page()

        try:
            # ── Step 1: Navigate to new story ─────────────────────────────────
            await log_step(run_id, "publisher", "Navigating to medium.com/new-story...")
            await page.goto("https://medium.com/new-story", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            # Confirm we're not on the login page
            if "signin" in page.url or "login" in page.url:
                raise RuntimeError(
                    "Session expired — re-run auth flow via POST /publisher/start-auth"
                )
            await log_step(run_id, "publisher", "Editor loaded ✓", level="success")

            # ── Step 2: Set title ─────────────────────────────────────────────
            await log_step(run_id, "publisher", f'Setting title: "{title[:60]}…"')
            title_el = await _find(page, _TITLE_SELECTORS, "title input")
            await title_el.click()
            await page.keyboard.press("Control+a")
            # Use execCommand for reliable contenteditable input
            await page.evaluate(
                "([text]) => document.execCommand('insertText', false, text)",
                [title],
            )
            await page.wait_for_timeout(500)
            await log_step(run_id, "publisher", "Title set ✓", level="success")

            # ── Step 3: Insert body ───────────────────────────────────────────
            word_count = len(content.split())
            await log_step(
                run_id, "publisher",
                f"Inserting body ({word_count} words) via clipboard paste..."
            )
            body_el = await _find(page, _BODY_SELECTORS, "body editor")
            await body_el.click()

            # Grant clipboard and paste
            await context.grant_permissions(["clipboard-read", "clipboard-write"])
            await page.evaluate(
                "async ([text]) => { await navigator.clipboard.writeText(text); }",
                [content],
            )
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Control+v")
            await page.wait_for_timeout(2000)
            await log_step(run_id, "publisher", "Body inserted ✓", level="success")

            # ── Step 4: Open publish panel ────────────────────────────────────
            await log_step(run_id, "publisher", "Opening publish panel...")
            publish_btn = page.get_by_role(
                "button", name=re.compile(r"^publish$", re.I)
            ).first
            if not await publish_btn.count():
                publish_btn = page.get_by_role(
                    "button", name=re.compile(r"publish", re.I)
                ).first
            await publish_btn.click()
            await page.wait_for_timeout(2000)
            await log_step(run_id, "publisher", "Publish panel open ✓", level="success")

            # ── Step 5: Add tags ──────────────────────────────────────────────
            await log_step(run_id, "publisher", f"Adding {len(tags[:5])} tags...")
            tag_input = await _find(page, _TAG_INPUT_SELECTORS, "tag input")
            for tag in tags[:5]:
                await tag_input.fill(tag)
                await page.keyboard.press("Enter")
                await page.wait_for_timeout(400)
            await log_step(run_id, "publisher", "Tags added ✓", level="success")

            # ── Step 6: Publish or save as draft ──────────────────────────────
            if publish_live:
                await log_step(run_id, "publisher", "Clicking 'Publish now'...")
                confirm = page.get_by_role(
                    "button", name=re.compile(r"publish now", re.I)
                ).first
                if not await confirm.count():
                    confirm = page.get_by_role(
                        "button", name=re.compile(r"^publish$", re.I)
                    ).nth(1)
                await confirm.click()
                await page.wait_for_timeout(4000)
            else:
                await log_step(run_id, "publisher", "Saving as draft (closing panel)...")
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(1500)

            url = page.url
            await log_step(
                run_id, "publisher",
                f"{'Published' if publish_live else 'Draft saved'}: {url}",
                level="success",
                data={"url": url, "publish_live": publish_live},
            )

            # Refresh session in case cookies were rotated
            updated = await context.storage_state()
            await _save_session(updated)

            return url

        except Exception as exc:
            await log_step(run_id, "publisher", f"Playwright error: {exc}", level="error")
            raise
        finally:
            await browser.close()


# ── Public entrypoint ──────────────────────────────────────────────────────────

async def publish_to_medium(
    run_id: str,
    title: str,
    content: str,
    tags: list[str],
    *,
    publish_live: bool = False,
) -> str:
    """Returns the Medium story URL (draft or published)."""
    if settings.medium_access_token:
        url = await _publish_via_api(run_id, title, content, tags, publish_live)
    else:
        url = await _publish_via_playwright(run_id, title, content, tags, publish_live)

    db = get_db()
    await db.posts.update_one(
        {"run_id": run_id},
        {"$set": {
            "medium_url": url,
            "status": "published" if publish_live else "draft_submitted",
            "published_at": datetime.now(UTC),
        }},
    )
    return url
