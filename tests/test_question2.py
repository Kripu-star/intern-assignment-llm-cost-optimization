from __future__ import annotations

import pytest

from eval.reference import TICKET_EXPECTATIONS
from question2.agent import SupportPipeline
from shared.kb import expanded_help_center_blob
from shared.tools import get_order, get_ticket

PUBLIC = ["T-1001", "T-1002", "T-1003", "T-1004"]
ALL = PUBLIC + ["T-1091"]


def test_help_center_exceeds_context():
    from shared.tokens import count_tokens

    assert count_tokens(expanded_help_center_blob()) > 200_000


@pytest.mark.parametrize("tid", ALL)
def test_pipeline_resolves_tickets(tid):
    expected = TICKET_EXPECTATIONS[tid]
    got = SupportPipeline().handle_ticket(tid)
    assert got.action == expected.action
    assert got.kb_article == expected.kb_article


@pytest.mark.parametrize("tid", ALL)
def test_retrieval_contains_correct_article(tid):
    """The simulator ignores article text, so check retrieval separately."""
    pipe = SupportPipeline()
    ticket = get_ticket(tid)
    _, query = pipe._triage(ticket, get_order(ticket["order_id"]))
    assert TICKET_EXPECTATIONS[tid].kb_article in pipe._retrieve(query)


@pytest.mark.parametrize("tid", ALL)
def test_cost_per_ticket_under_target(tid):
    pipe = SupportPipeline()
    pipe.handle_ticket(tid)
    assert pipe.session.total_points() <= 2500


def test_audit_rejects_invalid_output():
    pipe = SupportPipeline()
    retrieved = {"returns-within-30-days": "x"}
    for bad in ("not json", '{"action":"REFUND_ALL","kb_article":"returns-within-30-days"}',
                '{"action":"REFUND","kb_article":"made-up-article"}'):
        assert pipe._audit(bad, retrieved).action == "ESCALATE_TIER2"
