import asyncio
import os
from time import time

import httpx
from loguru import logger

from .gihub_api_wrapper.api_wrappers import get_files_in_dir, get_latest_release_name_url_and_datetime
from .gihub_api_wrapper.client_settings import httpx_client_settings
from .gihub_api_wrapper.utils import get_repo_name, get_repo_owner
from .wiki_parser.Article import Article
from .wiki_parser.front_matter_parser import extract_contributors_usernames, extract_dependencies
from .wiki_parser.GithubAccount import GithubAccount
from .wiki_parser.Release import Release
from .wiki_parser.Repo import Repo


async def get_dependency_map() -> list[Article]:
    t0 = time()
    logger.debug("Started gathering dependency map")
    async with httpx.AsyncClient(**httpx_client_settings) as client:
        article_files = await get_files_in_dir(
            client=client,
            repo_owner=os.environ["WIKI_REPO_OWNER"],
            repo_name=os.environ["WIKI_REPO_NAME"],
            dir_path="/docs/en",
        )
        logger.debug(f"Fetched {len(article_files)} articles in {round(time() - t0, 4)}s")
        dep_map = {article.name: extract_dependencies(article.content) for article in article_files}
        contributors_map = {article.name: extract_contributors_usernames(article.content) for article in article_files}
        repo_urls = []
        release_tasks = []
        for dependency_list in dep_map.values():
            for repo_name, repo_url in dependency_list:
                repo_urls.append(repo_url)
                repo_owner = get_repo_owner(repo_url)
                repo_name = get_repo_name(repo_url)
                release_tasks.append(
                    get_latest_release_name_url_and_datetime(client=client, repo_owner=repo_owner, repo_name=repo_name)
                )

        t1 = time()
        latest_releases = await asyncio.gather(*release_tasks)
        logger.debug(f"Fetched latest releases for {len(latest_releases)} repos in {round(time() - t1, 4)}s")

    repos = {}
    for repo_url, latest_release in zip(repo_urls, latest_releases):
        release_name, release_url, release_date = latest_release
        release = Release(
            name=release_name,
            url=release_url,
            date=release_date,
        )
        repo_name = get_repo_name(repo_url)
        base_repo_url = "/".join(repo_url.split("/")[:5])
        repo = Repo(name=repo_name, url=base_repo_url, latest_release=release)
        repos[repo_url] = repo

    articles = []
    for article_file in article_files:
        dependencies = [repos[repo_url] for _, repo_url in dep_map[article_file.name]]
        contributors = [GithubAccount(username=contributor) for contributor in contributors_map[article_file.name]]
        article = Article(
            filename=article_file.name,
            url=article_file.download_url,
            dependencies=dependencies,
            contributors=contributors,
            last_modified_date=article_file.last_modified_date,
        )
        articles.append(article)

    logger.debug(f"Dependency map gathering complete. Run time: {round(time() - t0, 4)}s")
    return articles
