import asyncio
import sqlite3
from time import time

import httpx
from loguru import logger

from .db_wrapper.db import connection as db_connection
from .gihub_api_wrapper.api_wrappers import create_new_issue
from .gihub_api_wrapper.client_settings import httpx_client_settings
from .wiki_parser.Article import Article
from .wiki_parser.DeprecationConflict import DeprecationConflict
from .wiki_parser.issue_generation import create_issue


def get_conflicts(articles: list[Article]) -> list[DeprecationConflict]:
    conflicts = []
    for article in articles:
        article_conflicts = article.get_conflicts()
        conflicts.extend(article_conflicts)
    logger.info(f"Detected {len(conflicts)} conflicts")
    return conflicts


def conflict_saved(conflict: DeprecationConflict, connection: sqlite3.Connection) -> bool:
    cursor = connection.cursor()
    statement = "SELECT * FROM conflicts WHERE hash=?;"
    cursor.execute(statement, (conflict.conflict_hash,))
    return bool(cursor.fetchone())


def save_conflict(conflict: DeprecationConflict, connection: sqlite3.Connection) -> None:
    cursor = connection.cursor()
    statement = "INSERT INTO conflicts VALUES (?, ?, ?, ?);"
    cursor.execute(statement, (conflict.conflict_hash, conflict.conflict_signature, True, False))


async def resolve_conflicts(conflicts: list[DeprecationConflict]) -> None:
    for conflict in conflicts:
        if conflict_saved(conflict, db_connection):
            logger.debug(f"Conflict {conflict.conflict_hash} found in DB. Ignoring")
            continue
        save_conflict(conflict, db_connection)
        db_connection.commit()
        logger.debug(f"Conflict {conflict.conflict_hash} registered as new and saved")
    await create_issues(conflicts)


async def post_issue(client: httpx.AsyncClient, conflict: DeprecationConflict, connection: sqlite3.Connection) -> str:
    issue = create_issue(conflict)
    issue_url: str = await create_new_issue(
        client=client,
        repo_owner=issue.repo_owner,
        repo_name=issue.repo_name,
        title=issue.title,
        body=issue.body,
        labels=["deprecation"],
        assignees=[c.username for c in conflict.article.contributors],
    )
    logger.info(f"New issue has been posted at {issue_url} for conflict {conflict.conflict_hash}")
    cursor = connection.cursor()
    statement = "UPDATE conflicts SET action_done=? WHERE hash=?;"
    cursor.execute(statement, (True, conflict.conflict_hash))
    logger.info(f"Conflict {conflict.conflict_hash} marked as resolved")
    return issue_url


def get_pending_conflicts_hashes(connection: sqlite3.Connection) -> set[str]:
    cursor = connection.cursor()
    statement = "SELECT hash FROM conflicts WHERE action_required=1 AND action_done=0;"
    cursor.execute(statement)
    return {result[0] for result in cursor.fetchall()}


async def create_issues(conflicts: list[DeprecationConflict]) -> list[str]:
    pending_conflicts_hashes = get_pending_conflicts_hashes(db_connection)
    logger.info(f"Found {len(pending_conflicts_hashes)} conflicts awaiting action")

    async with httpx.AsyncClient(**httpx_client_settings) as client:
        conflict_tasks = [
            post_issue(client=client, conflict=conflict, connection=db_connection)
            for conflict in conflicts
            if conflict.conflict_hash in pending_conflicts_hashes
        ]
        t0 = time()
        issue_urls: list[str] = await asyncio.gather(*conflict_tasks)
        logger.info(f"{len(conflict_tasks)} issues created in {round(time() - t0, 4)}")

    db_connection.commit()
    return issue_urls
