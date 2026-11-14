from __future__ import annotations

import json
import re
from dataclasses import dataclass

from shared.billing import CostSession
from shared.llm import ChatMessage, LlmClient
from shared.tools import get_order, get_ticket


@dataclass
class TicketResolution:
    action: str
    kb_article: str
    customer_reply: str
    raw_completion: str


def parse_resolution(text: str) -> TicketResolution:
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError(f"No JSON in model output:\n{text[:400]}")
    data = json.loads(m.group())
    return TicketResolution(
        action=str(data["action"]).upper(),
        kb_article=str(data["kb_article"]),
        customer_reply=str(data.get("customer_reply", "")),
        raw_completion=text,
    )


# Compact routing rules (one line per KB article) instead of full article text.
# Wording deliberately avoids phrases that trigger long free-text answers:
# output tokens cost 5x input tokens, so short output is the biggest saving.
_SYSTEM = """You are ShopAssist, a Tier-1 support copilot.
Pick one action: REFUND, REPLACE, SEND_ARTICLE, ESCALATE_TIER2. Cite one kb_article id.
Rules (first match wins):
- subscription: age<=30d REFUND else SEND_ARTICLE; subscription-cooling-off
- license_revealed: SEND_ARTICLE; digital-license-no-refund
- customized and damaged: ESCALATE_TIER2; custom-items-no-replace
- damaged, delivered<=7d: REPLACE; damage-replacement-7-days
- physical, unopened, delivered<=30d: REFUND; returns-within-30-days
- otherwise: ESCALATE_TIER2; returns-within-30-days
Reply with JSON only: {"action":..,"kb_article":..,"customer_reply":<one sentence>}"""

# Ticket metadata that does not affect routing.
_DROP_FIELDS = {"order_id", "sku"}


class SupportCopilot:
    """
    ShopAssist Tier-1 copilot (baseline).

    Given a support ticket + order snapshot, choose an action, cite the help-center
    article, and draft the customer reply.
    """

    def __init__(self, session: CostSession | None = None):
        self.session = session or CostSession()
        self.llm = LlmClient(self.session)

    def build_messages(self, ticket_id: str) -> list[ChatMessage]:
        ticket = get_ticket(ticket_id)
        order = get_order(ticket["order_id"])
        # Only customer messages carry information; agent filler is dropped.
        thread = "\n".join(
            m["text"] for m in ticket["messages"] if m["from"] == "customer"
        )
        facts = {k: v for k, v in order.items() if k not in _DROP_FIELDS}
        snapshot = json.dumps(facts, separators=(",", ":"))
        user = f"THREAD:\n{thread}\nORDER_SNAPSHOT:\n{snapshot}\nEND_SNAPSHOT"
        return [ChatMessage("system", _SYSTEM), ChatMessage("user", user)]

    def handle_ticket(self, ticket_id: str) -> TicketResolution:
        messages = self.build_messages(ticket_id)
        completion = self.llm.chat("handle_ticket", messages)
        return parse_resolution(completion)
