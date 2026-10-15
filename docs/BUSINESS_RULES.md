# Northstar Cloud business rules (version 1)

These are simulated SaaS records; no real payments are performed.

- Money is integer minor units, USD only in the initial fixture.
- An account belongs to one customer. Every service receives an authenticated
  customer ID; finding another customer's account returns the same not-found error.
- Accounts are ACTIVE or SUSPENDED. Only active accounts may perform mutations.
- Subscriptions are ACTIVE, PAST_DUE, or CANCELED. Only active subscriptions may
  change to an enabled plan; requesting the existing plan is rejected.
- Internal lifecycle transitions allow ACTIVE to PAST_DUE or CANCELED and
  PAST_DUE to ACTIVE or CANCELED. CANCELED is terminal. This internal service is
  not an additional model tool.
- Plans: Starter $19/month, Growth $49/month, Scale $99/month. Changes update the
  plan only; no proration or payment provider integration is claimed.
- Paid invoices dated no more than 30 days ago are eligible for a single full
  refund up to $100. Future-dated, unpaid, void, and refunded invoices are ineligible.
- Refunds preserve original payment status, persist a separate refund record,
  and set `refunded_minor` atomically. Partial refunds are not supported.
- A caller-provided idempotency key is scoped to the account. A replay returns the
  persisted result only if operation and arguments match. Reusing a key for
  different arguments is a conflict.
- Each mutation locks the account, then subscription/invoice. Audit and result
  records commit with the mutation. PostgreSQL row locks serialize competing
  requests; unique constraints and conditional updates provide a second guard.

The policy corpus in C03 must agree with these rules. Operator approval cannot
override ownership or financial eligibility. Missing records and conflicting
states are preserved in deterministic fixtures for later evaluation.
