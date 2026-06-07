"""
PublisherAgent — human-in-the-loop Medium publishing

Two paths (auto-selected):
  A. Medium API  — if MEDIUM_ACCESS_TOKEN is set in .env (recommended)
  B. Playwright  — headless browser with session persistence in MongoDB

Authentication (path B only, one-time setup):
  1. POST /publisher/start-auth   {"email": "you@example.com"}
     → triggers magic-link email from Medium
  2. Copy the link URL from your email (do NOT click it — just copy)
  3. POST /publisher/complete-auth {"magic_url": "https://medium.com/m/callback/..."}
     → Playwright navigates to that URL, session saved to MongoDB

Every action emits a log_step so the frontend terminal shows live progress.
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


# ── Auth flow (path B) ─────────────────────────────────────────────────────────

async def start_auth_flow(email: str) -> str:
    """
    Start a headless browser, navigate to Medium signin, enter the email.
    Medium will send a magic-link email.  Returns instructions for the user.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page    = await browser.new_page()

        await page.goto("https://medium.com/m/signin", wait_until="domcontentloaded")
        await page.wait_for_timeout(2000)

        # Click "Sign in with email"
        btn = page.get_by_text("Sign in with email", exact=False)
        if await btn.count():
            await btn.first.click()
            await page.wait_for_timeout(1500)

        # Enter email
        email_box = page.get_by_role("textbox").first
        await email_box.fill(email)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2000)

        await browser.close()

    return (
        f"Magic link sent to {email}. "
        "Open your email, right-click the link → Copy link address "
        "(do NOT click it), then call POST /publisher/complete-auth with the URL."
    )


async def complete_auth_flow(magic_url: str) -> str:
    """
    Open the magic link in a headless browser, wait for redirect to confirm
    authentication, then save the session to MongoDB.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context()
        page    = await context.new_page()

        await page.goto(magic_url, wait_until="networkidle", timeout=30_000)
        await page.wait_for_timeout(3000)

        # Verify we're logged in — Medium redirects to home or the story page
        current = page.url
        if "medium.com/m/signin" in current:
            await browser.close()
            raise RuntimeError("Magic link expired or already used. Restart auth flow.")

        storage = await context.storage_state()
        await _save_session(storage)
        await browser.close()

    return "Session saved. Medium publishing is now ready."


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
