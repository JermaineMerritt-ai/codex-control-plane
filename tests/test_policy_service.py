from services.policy_service import (
    PolicyCategory,
    classify_message_policy_category,
    evaluate_action,
)


def test_evaluate_read_only_and_draft_allowed_without_approval():
    for cat in (PolicyCategory.read_only, PolicyCategory.draft_only):
        ev = evaluate_action(cat)
        assert ev.allowed and not ev.blocked and not ev.requires_approval


def test_evaluate_outbound_and_publish_require_approval():
    for cat in (PolicyCategory.outbound_send, PolicyCategory.publish):
        ev = evaluate_action(cat)
        assert ev.allowed and not ev.blocked and ev.requires_approval


def test_evaluate_destructive_blocked():
    ev = evaluate_action(PolicyCategory.destructive)
    assert not ev.allowed and ev.blocked and not ev.requires_approval


def test_classify_message_heuristics():
    assert classify_message_policy_category("draft a script") is PolicyCategory.draft_only
    assert classify_message_policy_category("send email to the team") is PolicyCategory.outbound_send
    assert classify_message_policy_category("send an email to john@example.com now") is PolicyCategory.outbound_send
    assert classify_message_policy_category("publish this to youtube") is PolicyCategory.publish
    assert classify_message_policy_category("delete old records") is PolicyCategory.destructive
    assert classify_message_policy_category("list my emails") is PolicyCategory.read_only
