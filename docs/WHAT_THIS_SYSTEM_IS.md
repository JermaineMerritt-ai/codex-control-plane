# What this system is

**In one line:** a governed control plane that lets operators automate communication workflows **without losing control, context, or accountability**.

This is a **governed communications control plane**: software that accepts work, classifies risk, **requires human approval before irreversible outbound actions**, executes only what was approved, and leaves a **durable, inspectable trail** for operators.

> **This system treats each account/brand as a governed context with its own policies, tone, and approval rules.**

Different inboxes (e.g. business ops vs. other missions or communities) imply different risk and voice. The architecture is meant to grow toward **per-context policy and approval**—multi-tenant governance and brand-level control—rather than one undifferentiated automation behavior across every channel.

It is **not** an “AI assistant,” a generic “automation tool,” a “content bot,” a chatbot that “just sends email,” or an AI that acts on its own behalf.

---

## Problem it solves

Teams need to use AI and automation against real channels (email first) **without** silent sends, surprise side effects, or opaque failures. Today’s integrations often optimize for speed; this system optimizes for **control**: every sensitive path is explicit, queued, approved where policy says so, and recoverable when something breaks.

---

## Who it’s for

- **Operators** who must trust that sends and side effects only happen after review.
- **Builders** who want a **repeatable pattern** for the next channel, not a one-off script.
- **Anyone** who needs to say, with evidence: *what was requested, what was approved, what ran, and what failed.*

---

## What it controls

- **Intake** of work (e.g. chat-style requests) into **durable jobs**.
- **Policy**: what is allowed, blocked, or **gated for approval**.
- **Approval** as a first-class object—not an afterthought.
- **Execution** in workers, **after** approval, with **idempotency** and **dedupe** so retries do not double-send.
- **Inspection**: jobs, approvals, audit events, and domain records (e.g. deliveries) operators can query without digging through logs alone.

The first reference implementation is **Gmail** (read, draft, approval-gated send). The same **connector standard** applies to anything you add next.

---

## What it refuses to do

- **Autonomous outbound** without an explicit approval path where policy requires it.
- **Silent degradation** when “live” configuration is wrong (misconfigured providers fail fast).
- **One-size-fits-all behavior** across accounts or brands where policy, tone, or risk actually differ—until explicit per-context rules exist, operate **one governed context at a time** (e.g. one live proof per inbox), not merged or “multi-account intelligence” by default.
- **Scope creep** disguised as “one more integration”—new connectors must follow the same governance and acceptance bar, or they do not ship as part of this pattern.

Those refusals are intentional. They are how the system stays **operable** and **defensible**.

---

## Why governance matters

Without governance, “the model said so” becomes the audit trail. With governance, **people and systems share a contract**: policy states the rules, approvals record the decision, jobs and audit record the outcome. That is what makes the stack **infrastructure**—something you can scale, sell, or hand to another team—instead of a demo that only the author trusts.

---

## Where you are in the lifecycle

**Architecture and docs are in place.** The non-negotiable next step for *this* slice is a **live proof** (real account, real send, real failure/retry) using the operator checklist—so “validated design” becomes **validated operation**. After that, you choose **depth** (e.g. richer Gmail) or **port the pattern** (one new connector, same standard)—not both at once without discipline.

For the technical pattern, see [CONNECTOR_STANDARD.md](CONNECTOR_STANDARD.md). For operators, see [GMAIL_OPERATOR_RUNBOOK.md](GMAIL_OPERATOR_RUNBOOK.md) and [OPERATOR_ACCEPTANCE_CHECKLIST.md](OPERATOR_ACCEPTANCE_CHECKLIST.md).
