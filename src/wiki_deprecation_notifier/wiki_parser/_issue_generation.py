from __future__ import annotations

from typing import TYPE_CHECKING

from .Issue import Issue

if TYPE_CHECKING:
    from .DeprecationConflict import DeprecationConflict


def create_issue(conflict: DeprecationConflict) -> Issue:
    issue_title = "".join(  # noqa: ECE001
        (
            f"Article {conflict.article.name} is deprecated due to",
            f'a release "{conflict.dependency.latest_release.name}"',
            f'in "{conflict.dependency.name}".',
        )
    )
    issue_body = "".join(  # noqa: ECE001
        (
            f'Article ["{conflict.article.name}"]({conflict.article.url}) ',
            "has been automatically marked as deprecated due to ",
            f'a recent release ["{conflict.dependency.latest_release.name}"]({conflict.dependency.latest_release.url})',
            f'in ["{conflict.dependency.name}"]({conflict.dependency.url}).',
            "\n\n",
            "An action has been requested from the article contributors:\n",
            "\n".join(f"- {c.handle}" for c in conflict.article.contributors),
            "\n\n",
            f"Deprecation reference id: {conflict.conflict_hash}",
        )
    )
    return Issue(
        repo_owner="airalab",
        repo_name="robonomics-wiki",
        title=issue_title,
        body=issue_body,
    )
