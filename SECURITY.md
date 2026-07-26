# Security

## What this build does not do

**There is no authentication.** A workspace separates work; it does not protect it.
Anyone who can reach the HTTP port can open any workspace, read every model and
delete them. This is stated plainly in the interface as well, on the pages where it
matters.

That is a deliberate trade for a tool meant to run as `make up` on your own
machine. It becomes a serious problem the moment the port is reachable by anyone
else, so the server binds `127.0.0.1` by default and logs a warning when it is told
not to.

If you expose it, put something in front of it: `oauth-proxy` on OpenShift, or any
reverse proxy that authenticates. See [`deploy/README.md`](deploy/README.md).

## The AI key

`KE_LLM_KEY` never reaches the browser and is never written into a model file, a
history version or an export.

When a key is set, `KE_LLM_BASE_URL` must also be set. The server refuses AI calls
otherwise, because the endpoint would then be chosen by the page — and the key is
attached to whatever endpoint is chosen. Pinning it server-side means the key can
only ever travel to the one address the operator picked.

## What leaves the machine

Nothing, unless you switch AI assistance on and use it. There are no analytics, no
telemetry, no update check and no fonts or scripts fetched at runtime: vis-network
and Font Awesome are vendored into the image.

When AI assistance is on, the text you send from a suggest button goes to the
endpoint you configured, and you are shown that text before it is sent.

## Reporting something

Open an issue for anything already public. For anything not, contact the maintainer
directly rather than filing publicly.

Two things that are known and are not bugs: the absence of authentication, and the
fact that a pinned LLM endpoint is still an outbound network call from the host.
