<p align="center">
  <img src="docs/img/logo.svg" alt="Pennant — knowledge engineering studio" width="440">
</p>

<p align="center">

---

## What this is

A studio for building **knowledge models**: a domain or a document written as layers
of typed nodes joined by typed relationships, so that a check can be pointed at one
claim instead of at "the document". That distinction is the whole product — it is
the difference between a finding and an impression.

It was built out of frustration with what happens when you ask a general model to
reason about company material: it produces something fluent, confident and
unverifiable, and you cannot tell which parts it read and which parts it filled in.
The response here is not a better prompt. It is to make the structure explicit and
checkable first, and to let the model work against that structure rather than
against a pile of prose.

A model in Pennant says things like: this section makes this claim; this claim
creates this obligation on this owner by this date; this evidence would settle it;
this rule contradicts that one. Then the analyzers run against the graph, and what
comes back is specific enough to argue with.

Nothing here needs a language model. Every graph, check, ordering and export is
arithmetic over what you typed. AI assistance is optional, off by default, and adds
suggest buttons — never silent edits.

## Screenshots

<img width="1897" height="978" alt="penant" src="https://github.com/user-attachments/assets/e607d89c-25b5-4437-a678-d4912b06bd46" />

<img width="1896" height="947" alt="9" src="https://github.com/user-attachments/assets/fd976017-e275-4f26-976b-eb8e9deafad9" />
<img width="1867" height="963" alt="8" src="https://github.com/user-attachments/assets/73efaee4-0aba-4960-b23f-1aff86e90b55" />
<img width="1903" height="973" alt="6" src="https://github.com/user-attachments/assets/f9be57f7-266a-49fd-9954-3f3c4481a1e7" />
<img width="1868" height="971" alt="5" src="https://github.com/user-attachments/assets/041b82c2-e43e-49b5-ace0-f1cff77165f1" />
<img width="1896" height="973" alt="4" src="https://github.com/user-attachments/assets/03f297df-6830-44dd-9b41-474f161667c9" />
<img width="1885" height="962" alt="3" src="https://github.com/user-attachments/assets/b3431d91-a160-45a2-9f74-990126c0c345" />
<img width="1881" height="982" alt="2" src="https://github.com/user-attachments/assets/f9822297-2a7e-4796-9540-f2258f790276" />
<img width="1907" height="985" alt="1st" src="https://github.com/user-attachments/assets/a3604285-ea53-4789-ace4-6a43d00956c4" />
<img width="1877" height="937" alt="13" src="https://github.com/user-attachments/assets/ace97596-020c-431e-863e-849c45d97a60" />
<img width="1866" height="975" alt="12" src="https://github.com/user-attachments/assets/2e5557e8-867d-4a93-82a9-736e592180e0" />
<img width="1893" height="970" alt="10" src="https://github.com/user-attachments/assets/347d356b-9629-4c12-b1d2-9bb597450d17" />


## Quick start

```bash
docker compose up --build     # then open http://127.0.0.1:8080
```

Or natively, with Go 1.21+:

```bash
make up                       # builds and serves on 127.0.0.1:8080, data in ./data
```

There are no Go dependencies to download, so `go build` works offline. It binds
loopback by default, because a tool with no authentication should not be reachable
from the network until somebody deliberately says so.

Full instructions, including SELinux and volume permissions: [`INSTALL.md`](INSTALL.md).

| Variable | Default | What it does |
|---|---|---|
| `KE_ADDR` | `127.0.0.1:8080` | Listen address |
| `KE_DATA` | `./data` | Workspace directory. Plain JSON, one file per thing |
| `KE_KEEP_VERSIONS` | `50` | History versions kept per file; `0` keeps everything |
| `KE_LLM_BASE_URL` | — | Any OpenAI-compatible endpoint. Pinning this is required if a key is set |
| `KE_LLM_MODEL` | — | Default model alias |
| `KE_LLM_KEY` | — | Sent to the pinned endpoint only. Never reaches the browser |

## Self-hosting

### Container

```bash
podman build -t pennant:0.13.0-ce .
podman run --rm -p 8080:8080 \
  -e KE_ADDR=0.0.0.0:8080 \
  -v ./data:/data:Z \
  pennant:0.13.0-ce
```

The `:Z` matters if SELinux is enforcing; without it the container cannot write the
volume and the server will refuse to start rather than fail on your first save an
hour later.

### Kubernetes and OpenShift

```bash
oc apply -k deploy/            # Route included
```

Read [`deploy/README.md`](deploy/README.md) first. The short version: **`replicas`
must stay at 1.** Storage serialises writes with a per-process mutex, so two pods
on one volume would interleave writes to the same JSON files with no locking and no
detection — silent corruption rather than an error. Scaling is a storage-driver
change, not a replica count.

And there is no authentication. On an internal Route that may be acceptable; exposed
it is not. See [`SECURITY.md`](SECURITY.md).

## Your data

`<KE_DATA>/profiles/<workspace>/*.json`, plus timestamped copies under
`.history/`. Readable, diffable, and committable with ordinary tools while the
application is running. That is deliberate: the format is the interface, and a
database would have taken that away for nothing you needed.

Nothing leaves the machine unless you switch AI assistance on and use it. No
telemetry, no update check, no fonts or scripts fetched at runtime.

## Templates

A template is just a model file. Anything that opens is a template, so sharing one
is sharing a `.json`.

- Browse and contribute: [`templates/`](templates/) — one worked example to start with

- Generate one from your own material with a capable model, then import it:
  [`prompts/generate-model.md`](prompts/generate-model.md)

That prompt is the piece worth reading even if you never contribute. It puts the
division of labour the right way round — the big model reads, Pennant holds the
structure and runs the checks — and it makes the model declare which parts it
inferred rather than read.

## Validating a model

```bash
python3 tools/model-v2.py --check  models/*.json    # report, change nothing
python3 tools/model-v2.py --write  models/*.json    # upgrade to schemaVersion 2
```

It reports dangling edges, undeclared layers, analyzers pointed at kinds they do
not check, logic cycles, pipeline inputs nothing produces — and, as warnings,
claims with no evidence behind them. That last list is usually the reason you built
the model.

## Development

```bash
node tools/smoke.js       web/*.html    # every inline script executes in a stub DOM
node tools/test_analyzers.js            # analyzer scoping
node tools/test_llm_panel.js            # AI panel and config resolution
node tools/test_landing.js              # landing page drawing
node tools/test_import.js               # templates and the AI prompt really import
go vet ./... && go build ./...
```

The frontend is one HTML file with one inline `<script>`, on purpose: no build step,
no bundler, no `node_modules`, and you can read the whole thing. Keep it to one
script block — `tools/smoke.js` handles more, but the single block is what makes
the file navigable.

## Licence

MIT. Copyright (c) 2026 Luka Gale. See [`LICENSE`](LICENSE) and
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).

There is one edition and this is it. Use it, change it, ship it, sell it, fork it and
never say where it came from — keep the copyright notice in the copies and that is the
entire obligation. No warranty and no support commitment, which is the other half of
the same deal.

The feature flags in the source hide unfinished surfaces, not paid ones. Nothing is
withheld from this build to create a better one, because there is no better one.
