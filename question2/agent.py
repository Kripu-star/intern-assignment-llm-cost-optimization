from __future__ import annotations

import json
import re
from dataclasses import dataclass

from shared.billing import CostSession
from shared.kb import article_ids, load_article
from shared.llm import ChatMessage, LlmClient
from shared.tools import get_order, get_ticket

from question1.agent import parse_resolution

ACTIONS = {"REFUND", "REPLACE", "SEND_ARTICLE", "ESCALATE_TIER2"}
TOP_K = 3

# Order fields that do not affect routing.
_DROP_FIELDS = {"order_id", "sku"}

# Words to add to the retrieval query for each order flag.
_FLAG_WORDS = {
    "damage_reported": "damaged damage replacement",
    "customized": "custom personalized",
    "license_revealed": "digital license",
    "opened": "opened",
}

_SYSTEM = """You are ShopAssist, a Tier-1 support copilot.
Pick one action: REFUND, REPLACE, SEND_ARTICLE, ESCALATE_TIER2. Cite one kb_article id from the articles.
Reply with JSON only: {"action":..,"kb_article":..,"customer_reply":<one sentence>}"""


@dataclass
class TicketResolution:
    action: str
    kb_article: str


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


class SupportPipeline:
    """triage -> retrieve -> compose -> audit.

    Only `compose` calls the LLM. Triage, retrieve and audit are deterministic
    code: they need no language understanding, so paying tokens for them is waste.
    """

    def __init__(self, session: CostSession | None = None):
        self.session = session or CostSession()
        self.llm = LlmClient(self.session)
        # Real articles only. The ~210k-token "expanded help center" is filler
        # and is never sent to the model.
        self.articles = {aid: load_article(aid) for aid in article_ids()}

    def handle_ticket(self, ticket_id: str) -> TicketResolution:
        ticket = get_ticket(ticket_id)
        order = get_order(ticket["order_id"])

        facts, query = self._triage(ticket, order)
        retrieved = self._retrieve(query)
        draft = self._compose(facts, retrieved)
        return self._audit(draft, retrieved)

    # -- node 1: triage (code) ------------------------------------------
    def _triage(self, ticket: dict, order: dict) -> tuple[dict, str]:
        thread = "\n".join(
            m["text"] for m in ticket["messages"] if m["from"] == "customer"
        )
        facts = {k: v for k, v in order.items() if k not in _DROP_FIELDS}
        flag_words = " ".join(w for f, w in _FLAG_WORDS.items() if order.get(f))
        query = f"{thread} {order.get('product_type', '')} {flag_words}"
        return {"thread": thread, "order": facts}, query

    # -- node 2: retrieve (code) ----------------------------------------
    def _retrieve(self, query: str) -> dict[str, str]:
        q = _words(query)
        scored = sorted(
            self.articles,
            key=lambda a: len(q & _words(a.replace("-", " ") + " " + self.articles[a])),
            reverse=True,
        )
        return {a: self.articles[a] for a in scored[:TOP_K]}

    # -- node 3: compose (the only LLM call) -----------------------------
    def _compose(self, facts: dict, retrieved: dict[str, str]) -> str:
        # Drop each article's "# id" heading line; the id is shown in brackets instead.
        articles = "\n".join(
            f"[{aid}] {text.split(chr(10), 1)[1].strip()}"
            for aid, text in retrieved.items()
        )
        snapshot = json.dumps(facts["order"], separators=(",", ":"))
        user = (
            f"ARTICLES:\n{articles}\n"
            f"THREAD:\n{facts['thread']}\n"
            f"ORDER_SNAPSHOT:\n{snapshot}\nEND_SNAPSHOT"
        )
        return self.llm.chat(
            "compose", [ChatMessage("system", _SYSTEM), ChatMessage("user", user)]
        )

    # -- node 4: audit (code) --------------------------------------------
    def _audit(self, draft: str, retrieved: dict[str, str]) -> TicketResolution:
        """Validate the draft; never let a malformed or invented answer through."""
        try:
            parsed = parse_resolution(draft)
        except (ValueError, KeyError, json.JSONDecodeError):
            return TicketResolution("ESCALATE_TIER2", next(iter(retrieved)))
        if parsed.action not in ACTIONS or parsed.kb_article not in self.articles:
            return TicketResolution("ESCALATE_TIER2", next(iter(retrieved)))
        return TicketResolution(parsed.action, parsed.kb_article)
