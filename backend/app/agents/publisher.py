"""
PublisherAgent

Publishes the final post to Medium using Playwright browser automation.
Leaves [IMAGE: ...] markers in place so the author can replace them
with real images after publishing (or manually before).

Strategy:
  1. Log in via email/password (session-cached for the run)
  2. Navigate to new story
  3. Set title
  4. Paste content (Medium accepts rich text / markdown-ish input)
  5. Add tags
  6. Publish as draft (safe default) — caller can set publish=True for live
"""

import re
import time
from typing import Any

from playwright.async_api import Browser, Page, async_playwright

from app.config import settings
from app.database import get_db


async def publish_to_medium(
    run_id: str,
    title: str,
    content: str,
    tags: list[str],
    *,
    publish_live: bool = False,
) -> str:
    """Returns the Medium story URL (draft or published)."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()

        try:
            await _login(page)
            url = await _create_story(page, title, content, tags, publish_live)
            await _record_publish(run_id, url, publish_live)
            return url
        finally:
            await browser.close()


async def _login(page: Page) -> None:
    await page.goto("https://medium.com/m/signin", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    # Click "Sign in with email"
    email_btn = page.get_by_text("Sign in with email", exact=False)
    if await email_btn.count() > 0:
        await email_btn.click()
        await page.wait_for_timeout(1000)

    email_input = page.get_by_role("textbox").first
    await email_input.fill(settings.medium_user_email)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(1500)

    pw_input = page.get_by_role("textbox", name=re.compile("password", re.I))
    await pw_input.fill(settings.medium_user_password)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(3000)


async def _create_story(
    page: Page,
    title: str,
    content: str,
    tags: list[str],
    publish_live: bool,
) -> str:
    await page.goto("https://medium.com/new-story", wait_until="domcontentloaded")
    await page.wait_for_timeout(2000)

    # Title
    title_area = page.get_by_role("textbox", name=re.compile("title", re.I))
    await title_area.click()
    await title_area.fill(title)
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(500)

    # Body — write paragraph by paragraph for Medium's block editor
    body_area = page.get_by_role("textbox").nth(1)
    await body_area.click()

    paragraphs = _split_content(content)
    for para in paragraphs:
        await body_area.type(para, delay=5)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(100)

    await page.wait_for_timeout(2000)

    # Open publish panel
    publish_btn = page.get_by_role("button", name=re.compile("publish", re.I))
    await publish_btn.click()
    await page.wait_for_timeout(1500)

    # Add tags
    tag_input = page.get_by_role("textbox", name=re.compile("tag|topic", re.I))
    for tag in tags[:5]:
        await tag_input.fill(tag)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(300)

    if publish_live:
        confirm_btn = page.get_by_role("button", name=re.compile("^publish", re.I), exact=False)
        await confirm_btn.click()
        await page.wait_for_timeout(3000)
    else:
        # Save as draft — navigate away after tagging
        await page.keyboard.press("Escape")

    current_url = page.url
    return current_url


def _split_content(content: str) -> list[str]:
    """Split markdown content into Medium-friendly paragraphs."""
    lines = content.split("\n")
    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Convert markdown headers to uppercase text (Medium handles H2/H3)
        if stripped.startswith("## "):
            result.append(stripped[3:].upper())
        elif stripped.startswith("### "):
            result.append(stripped[4:])
        else:
            result.append(stripped)
    return result


async def _record_publish(run_id: str, url: str, live: bool) -> None:
    db = get_db()
    await db.posts.update_one(
        {"run_id": run_id},
        {
            "$set": {
                "medium_url": url,
                "status": "published" if live else "draft_submitted",
            }
        },
    )
