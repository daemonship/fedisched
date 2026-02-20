"""Background scheduler for publishing scheduled posts."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlmodel import Session, select

from app.database import engine
from app.encryption import decrypt_credential
from app.models import Account, ScheduledPost
from app.platforms import mastodon as mastodon_platform
from app.platforms import bluesky as bluesky_platform

logger = logging.getLogger(__name__)


class PostScheduler:
    """Manages the background scheduler for publishing scheduled posts."""

    def __init__(self) -> None:
        self.scheduler = BackgroundScheduler(
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 30,
            }
        )
        self._job = None

    def start(self) -> None:
        """Start the scheduler and add the polling job."""
        if self._job is not None:
            logger.warning("Scheduler already started")
            return

        # Reset any 'publishing' posts back to 'scheduled' on startup
        # (in case the container restarted mid‑processing)
        self._reset_stuck_posts()

        # Add the job that runs every 30 seconds
        self._job = self.scheduler.add_job(
            self.process_due_posts,
            trigger=IntervalTrigger(seconds=30),
            id="process_due_posts",
            name="Process due scheduled posts",
            replace_existing=True,
        )

        self.scheduler.start()
        logger.info("Background scheduler started (interval: 30 seconds)")

    def shutdown(self) -> None:
        """Gracefully shutdown the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("Background scheduler stopped")

    def _reset_stuck_posts(self) -> None:
        """Reset any posts stuck in 'publishing' status back to 'scheduled'.

        This ensures that posts that were being processed when the container
        restarted are retried.
        """
        with Session(engine) as session:
            stuck_posts = session.exec(
                select(ScheduledPost).where(ScheduledPost.status == "publishing")
            ).all()
            for post in stuck_posts:
                post.status = "scheduled"
                session.add(post)
                logger.info(
                    "Reset stuck post %s from 'publishing' back to 'scheduled'",
                    post.id,
                )
            session.commit()
            if stuck_posts:
                logger.info("Reset %d stuck post(s)", len(stuck_posts))

    def process_due_posts(self) -> None:
        """Poll the database for due posts and publish them.

        A post is 'due' if its status is 'scheduled' and scheduled_at <= now.
        Each post is published to its associated account; on success the post
        is marked published, on failure it is either retried (with exponential
        backoff) or marked failed after 3 attempts.
        """
        logger.debug("Polling for due posts...")
        with Session(engine) as session:
            # Fetch due posts (status = 'scheduled', scheduled_at <= now)
            now = datetime.now(timezone.utc)
            due_posts = session.exec(
                select(ScheduledPost)
                .where(ScheduledPost.status == "scheduled")
                .where(ScheduledPost.scheduled_at <= now)
                .order_by(ScheduledPost.scheduled_at)
            ).all()

            if not due_posts:
                logger.debug("No due posts found")
                return

            logger.info("Processing %d due post(s)", len(due_posts))
            for post in due_posts:
                self._process_post(session, post)

    def _process_post(self, session: Session, post: ScheduledPost) -> None:
        """Process a single scheduled post.

        Changes the post status to 'publishing' while processing, then to
        either 'published' or 'failed' (or back to 'scheduled' with a later
        scheduled_at for retries).
        """
        # Mark as publishing to prevent another job from picking it up
        post.status = "publishing"
        session.add(post)
        session.commit()
        session.refresh(post)

        # Fetch the associated account
        account = session.get(Account, post.account_id)
        if not account:
            logger.error(
                "Account %d for post %d not found, marking as failed",
                post.account_id,
                post.id,
            )
            post.status = "failed"
            post.last_error = f"Account {post.account_id} not found"
            session.add(post)
            session.commit()
            return

        # Attempt to publish
        success, error, published_url = self._publish_to_account(post, account)

        if success:
            post.status = "published"
            post.published_at = datetime.now(timezone.utc)
            post.last_error = None
            session.add(post)
            session.commit()
            logger.info(
                "Post %d published successfully to %s account %s",
                post.id,
                account.platform,
                account.id,
            )
        else:
            # Determine whether to retry
            if post.retry_count < 3:
                # Exponential backoff: 2^retry_count minutes
                delay_minutes = 2 ** post.retry_count
                new_scheduled_at = datetime.now(timezone.utc) + timedelta(
                    minutes=delay_minutes
                )
                post.retry_count += 1
                post.last_error = error
                post.scheduled_at = new_scheduled_at
                post.status = "scheduled"
                session.add(post)
                session.commit()
                logger.warning(
                    "Post %d failed (attempt %d), retrying in %d minutes: %s",
                    post.id,
                    post.retry_count,
                    delay_minutes,
                    error,
                )
            else:
                # Max retries reached → permanent failure
                post.status = "failed"
                post.last_error = error
                session.add(post)
                session.commit()
                logger.error(
                    "Post %d failed permanently after %d attempts: %s",
                    post.id,
                    post.retry_count,
                    error,
                )

    @staticmethod
    def _publish_to_account(
        post: ScheduledPost,
        account: Account,
    ) -> tuple[bool, Optional[str], Optional[str]]:
        """Publish a post to a single account.

        Returns (success, error_message, published_url).
        """
        try:
            credentials = decrypt_credential(account.encrypted_credentials)

            if account.platform == "mastodon":
                published_url = mastodon_platform.post_status(
                    account.instance_url,
                    credentials,
                    post.content,
                )
                return True, None, published_url

            elif account.platform == "bluesky":
                published_url = bluesky_platform.post_status(credentials, post.content)
                return True, None, published_url

            else:
                return False, f"Unsupported platform: {account.platform}", None

        except ValueError as e:
            logger.error(
                "Failed to publish post %s to account %s: %s",
                post.id,
                account.id,
                e,
            )
            return False, str(e), None
        except Exception as e:
            logger.error("Unexpected error publishing post %s: %s", post.id, e)
            return False, f"Unexpected error: {e}", None


# Global scheduler instance
scheduler = PostScheduler()


def start_scheduler() -> None:
    """Start the background scheduler (called from FastAPI lifespan)."""
    scheduler.start()


def stop_scheduler() -> None:
    """Stop the background scheduler (called from FastAPI lifespan)."""
    scheduler.shutdown()