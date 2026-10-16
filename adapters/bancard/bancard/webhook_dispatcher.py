"""Outbound signed webhook dispatcher with retry policy and persistent dead-letter queue."""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy.orm import Session

from bancard.config import settings
from bancard.crypto import sign_vibecore_webhook
from bancard.database import DeadLetterWebhook
from bancard.metrics import metrics

logger = logging.getLogger("bancard.webhook_dispatcher")


class WebhookDispatcher:
    def __init__(
        self,
        secret: Optional[str] = None,
        timeout: float = 5.0,
        max_retries: int = 3,
        backoff_factor: float = 0.05,
    ) -> None:
        self.secret = secret or settings.vibecore_webhook_secret
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def dispatch_event(
        self,
        db: Session,
        event_type: str,
        data: Dict[str, Any],
        target_urls: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Dispatches signed event to downstream consumers with exponential backoff and dead-letter queueing.
        """
        urls = target_urls if target_urls is not None else settings.downstream_webhook_urls
        if not urls:
            logger.info("No downstream webhook URLs configured; skipping dispatch.")
            return []

        payload_obj = {
            "event_id": f"evt_{uuid.uuid4().hex}",
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        payload_bytes = json.dumps(payload_obj, separators=(",", ":"), sort_keys=True).encode("utf-8")
        ts = int(time.time())
        signature = sign_vibecore_webhook(self.secret, payload_bytes, timestamp=ts)

        headers = {
            "Content-Type": "application/json",
            "X-VibeCore-Signature": signature,
            "X-VibeCore-Timestamp": str(ts),
            "User-Agent": f"{settings.service_name}/{settings.service_version}",
        }

        results = []
        for url in urls:
            res = self._send_with_retry(
                db=db,
                target_url=url,
                event_type=event_type,
                payload_bytes=payload_bytes,
                signature=signature,
                headers=headers,
            )
            results.append(res)

        return results

    def _send_with_retry(
        self,
        db: Session,
        target_url: str,
        event_type: str,
        payload_bytes: bytes,
        signature: str,
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        attempts = 0
        last_error = ""

        while attempts < self.max_retries:
            attempts += 1
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    resp = client.post(target_url, content=payload_bytes, headers=headers)
                    if resp.status_code < 400:
                        metrics.record_webhook_dispatch("success")
                        logger.info(
                            "Webhook delivered successfully",
                            extra={"target_url": target_url, "attempt": attempts, "status_code": resp.status_code},
                        )
                        return {"target_url": target_url, "status": "delivered", "attempts": attempts}
                    else:
                        last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                        logger.warning(
                            "Webhook delivery non-2xx response",
                            extra={"target_url": target_url, "attempt": attempts, "error": last_error},
                        )
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {str(exc)}"
                logger.warning(
                    "Webhook delivery network exception",
                    extra={"target_url": target_url, "attempt": attempts, "error": last_error},
                )

            if attempts < self.max_retries:
                time.sleep(self.backoff_factor * (2 ** (attempts - 1)))

        # Exhausted all attempts -> Route to Dead-Letter Queue
        metrics.record_webhook_dispatch("failed")
        dl = DeadLetterWebhook(
            target_url=target_url,
            event_type=event_type,
            payload=payload_bytes.decode("utf-8"),
            signature=signature,
            attempts=attempts,
            last_attempt_at=datetime.now(timezone.utc),
            error_message=last_error,
            status="FAILED",
        )
        db.add(dl)
        db.commit()

        # Update dead letter count in metrics
        count = db.query(DeadLetterWebhook).filter(DeadLetterWebhook.status == "FAILED").count()
        metrics.set_dead_letter_count(count)

        logger.error(
            "Webhook delivery failed permanently; persisted to dead-letter queue",
            extra={"target_url": target_url, "dead_letter_id": dl.id, "error": last_error},
        )
        return {"target_url": target_url, "status": "dead_letter", "dead_letter_id": dl.id, "error": last_error}

    def retry_dead_letter(self, db: Session, dead_letter_id: str) -> bool:
        """Manually or automatically retry sending a dead-letter webhook."""
        dl = db.query(DeadLetterWebhook).filter(DeadLetterWebhook.id == dead_letter_id).first()
        if not dl or dl.status != "FAILED":
            return False

        headers = {
            "Content-Type": "application/json",
            "X-VibeCore-Signature": dl.signature,
            "User-Agent": f"{settings.service_name}/{settings.service_version}",
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(dl.target_url, content=dl.payload.encode("utf-8"), headers=headers)
                dl.attempts += 1
                dl.last_attempt_at = datetime.now(timezone.utc)
                if resp.status_code < 400:
                    dl.status = "REPROCESSED"
                    db.commit()
                    count = db.query(DeadLetterWebhook).filter(DeadLetterWebhook.status == "FAILED").count()
                    metrics.set_dead_letter_count(count)
                    return True
                else:
                    dl.error_message = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    db.commit()
                    return False
        except Exception as exc:
            dl.attempts += 1
            dl.last_attempt_at = datetime.now(timezone.utc)
            dl.error_message = f"{type(exc).__name__}: {str(exc)}"
            db.commit()
            return False


dispatcher = WebhookDispatcher()
