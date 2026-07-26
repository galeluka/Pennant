# The AI tier — what enforces it, and what only looks like it does

## 1. Your assumption is right in direction, wrong about one thing

Yes, it is a backend wrapper. No, it is not enforced yet — and the gate I added
in `web/index.html` must not be mistaken for enforcement.

`llmOn()` now reads `can('ai') && …`, so on a plan without AI the suggest buttons
disappear. That is a **product** gate: it stops the app offering something the
plan does not include, which is the same rule the Analyzers page follows for an
inapplicable analyzer. It is not a **revenue** gate. It is bypassed by opening
devtools and typing `state.plan='ce'`, or by skipping the page entirely:

```
curl -X POST http://host/api/llm/chat -d '{"model":"...","messages":[...]}'
```

Both reach `handleLLM` and both spend your inference budget. Anything that runs
in the browser is advisory, for the same reason the JSON import checks are
advisory: the person you are gating controls the code doing the gating.

## 2. What CE enforces today (verified in `main.go`)

Credit where it is due — the key handling is careful, and more careful than most:

| Check | Where | Verdict |
|---|---|---|
| Method must be POST | `handleLLM:504` | fine |
| Request body capped at 1 MB | `handleLLM:514` | fine |
| Scheme restricted to http/https with a host | `llmURL:422` | fine |
| **Requested `baseUrl` ignored when `KE_LLM_BASE_URL` is pinned** | `llmEndpoint:408` | good — a caller cannot redirect your key |
| **Refuses to start if a key is set with no pinned base** | `llmEndpoint:411` | genuinely good. Most implementations send the key wherever they are told |

What is absent, and all of it matters only once someone else is paying:

- **No authentication.** The endpoint does not know who is calling.
- **No plan check.** Nothing server-side consults an entitlement.
- **No quota and no metering.** No token accounting of any kind.
- **No per-tenant key attribution.** One `KE_LLM_KEY` serves every caller.

None of these are bugs in CE. On your own machine, calling your own endpoint with
your own key, every one of them would be wrong to add.

## 3. The framing that makes the tier defensible

"Pay for AI mode" is the wrong description and it will get argued with. The real
question is **whose key is it**:

| | Endpoint | Key | Who pays inference | Gate |
|---|---|---|---|---|
| Self-hosted | yours | yours | you | **none** — `ce.ai` is `true` |
| Hosted | ours | ours | us | metered and paid |

So it is not a paywall around a feature. It is **cost recovery on a variable
cost** — the only thing in the product with a real marginal cost per use. That is
the most defensible paid line you have, and it is much easier to say out loud:
*we are not charging you for the button, we are charging you for the tokens.*

Two consequences worth taking:

**BYOK on the free hosted tier.** If a free user supplies their own key, the
marginal cost to you is zero, so there is no reason to withhold it. It costs you
nothing, it removes the only complaint the free tier would attract, and it means
`can('ai')` should really be `can('ai') || userSuppliedKey`.

**A boolean entitlement is not enough.** `studio.ai = true` with no quota is an
unbounded liability: one user in a retry loop can cost more in a week than the
subscription earns in a year. Inference is metered per token, so the entitlement
has to be too — `aiTokensPerMonth`, not `ai: true`. This is the single thing I
would change in what I built before charging anybody.

## 4. The wrapper, concretely

Middleware in front of CE's handler, in the cloud repo, never in CE:

```
request → session         (who is this? 401 if nobody)
        → tenant          (which workspace, which plan)
        → entitlement     (does the plan include AI at all? 402 if not)
        → quota           (tokens left this period? 429 if not)
        → CE handleLLM    (unchanged: pins the endpoint, attaches the key)
        → meter           (read usage from the response, write it back)
        → response
```

Every step is additive and CE stays untouched, which is the whole point of
extracting `internal/server` first. The meter step needs the token counts from
the provider response body, so the wrapper has to read the response rather than
proxy it opaquely — worth knowing before you pick a streaming design, because
metering a stream is meaningfully harder than metering a single response.

Where the plan comes from: `/api/capabilities`, server-side, derived from the
session. `state.plan` then stops being a local override and becomes a cache of
what the server said. The Admin page switcher should be hidden whenever
`edition !== 'ce'` — it exists to test tiers locally, and on a hosted deployment
it would be a client asserting its own entitlement, which is exactly the thing
this document is about.

## 5. One finding that is not about billing

`llmURL` (`main.go:422`) checks scheme and host and nothing else. When
`KE_LLM_BASE_URL` is **not** pinned, the caller chooses the URL and the server
fetches it. On a laptop that is a feature — it is how you point the tool at
Ollama. On a hosted deployment it is a server-side request forgery primitive: a
caller can aim it at `http://169.254.169.254/`, at a cluster-internal service, or
at anything else reachable from the pod, and read the response through the error
message.

The hosted build must therefore either pin `KE_LLM_BASE_URL` and refuse any
requested override outright, or deny-list link-local, loopback and RFC1918
ranges after resolution — resolution matters, because a hostname that resolves to
`127.0.0.1` passes a string check. Pinning is simpler and is what a hosted
deployment wants anyway.

This one is worth fixing regardless of the pricing decision.
