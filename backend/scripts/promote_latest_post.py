#!/usr/bin/env python3
"""Promotes the most recent post (or a specific post_id) to exemplar status.

Usage:
    python scripts/promote_latest_post.py
    python scripts/promote_latest_post.py --post-id <mongodb_id>
    python scripts/promote_latest_post.py --list
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from app.agents.exemplar_store import promote_post_to_exemplar


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--post-id", help="MongoDB post run_id to promote")
    parser.add_argument("--list", action="store_true", help="List last 5 posts with scores")
    args = parser.parse_args()

    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    client: AsyncIOMotorClient = AsyncIOMotorClient(uri)
    db = client["medium_agent"]

    if args.list:
        posts = await db.posts.find(
            {}, {"title": 1, "quality_score": 1, "created_at": 1}
        ).sort("created_at", -1).limit(5).to_list(5)
        for p in posts:
            print(f"{p['_id']} | score={p.get('quality_score','?')} | {p.get('title','?')[:60]}")
        client.close()
        return

    if args.post_id:
        run_id = args.post_id
        latest = await db.posts.find_one({"run_id": run_id}, {"title": 1, "quality_score": 1})
        if not latest:
            print(f"No post found with run_id: {run_id}")
            client.close()
            return
        print(f"Post: {latest.get('title','?')} (score={latest.get('quality_score','?')})")
    else:
        latest = await db.posts.find_one({}, sort=[("created_at", -1)])
        if not latest:
            print("No posts found.")
            client.close()
            return
        run_id = str(latest.get("run_id", latest["_id"]))
        print(f"Latest: {latest.get('title','?')} (score={latest.get('quality_score','?')})")

    result = await promote_post_to_exemplar(run_id)
    print(f"{'Promoted' if result else 'Not promoted'}: {run_id}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
