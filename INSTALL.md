# Install and test locally

Everything here runs on your own machine and writes to a directory you choose.
Nothing is published anywhere and there is no telemetry, no update check and no
network call at runtime.

## Docker

```bash
docker compose up --build
# then open http://127.0.0.1:8080
```

The workspace lands in `./data` on your host as plain JSON:

```
data/profiles/<workspace>/models.json
data/profiles/<workspace>/perspectives.json
data/profiles/<workspace>/.history/models/20260725T143205Z.json
```

Read them, diff them, put the directory under git. That is the whole reason the
format is one readable file per thing rather than a database.

The port is published on `127.0.0.1` on purpose. **There is no authentication in
this build**, so binding all interfaces would publish every workspace to your LAN.
Change that only when you have put something in front of it — see `SECURITY.md`.

### First run

1. Open http://127.0.0.1:8080
2. Create a workspace. It is a folder, not an account: no password, no identity
   provider, and it separates work rather than protecting it.
3. **Admin → Load sample data** brings in the two models under `samples/`.
4. Open **Analyzers**. With the document template loaded, all ten analyzers apply.
   Switch to a model with no chapters or claims and watch them switch off, with the
   reason shown rather than the option hidden.

### Permissions

If the container cannot write `/data`, the server refuses to start and says so,
rather than failing on your first save an hour later. Two usual causes:

```bash
# SELinux (Fedora, RHEL): the bind mount needs a relabel
# compose.yaml uses ./data:/data — add :Z if enforcing
sudo chcon -Rt svirt_sandbox_file_t ./data

# ownership: the image runs as uid 65532
mkdir -p data && sudo chown -R 65532:65532 data
```

Rootless Podman maps uids differently and usually needs neither.

## Without Docker

```bash
go build -o pennant . && ./pennant --data ./data
# or
make up
```

Go 1.21 or newer. There are no third-party Go dependencies, so `go build` works
offline: no module download, no supply chain beyond the standard library.

## Configuration

| Variable | Flag | Default | Meaning |
|---|---|---|---|
| `KE_ADDR` | `--addr` | `127.0.0.1:8080` | Listen address |
| `KE_DATA` | `--data` | `./data` | Workspace directory |
| `KE_KEEP_VERSIONS` | `--keep` | `50` | History versions per file; `0` keeps all |
| `KE_LLM_BASE_URL` | — | unset | Any OpenAI-compatible endpoint |
| `KE_LLM_MODEL` | — | unset | Default model alias |
| `KE_LLM_KEY` | — | unset | Never reaches the browser |

The variables are still `KE_*`. Renaming them means renaming the on-disk contract
too, so it is a deliberate separate step rather than something bundled with a
rename of the product.

### AI assistance

Optional, off until you switch it on in **Profile → AI assistance**. Everything
else works without it: every graph, check, ordering and export is arithmetic over
what you typed.

Point it at anything OpenAI-compatible. For a local model with nothing to leak:

```bash
ollama serve
# compose.yaml:
#   KE_LLM_BASE_URL: "http://host.docker.internal:11434/v1"
#   KE_LLM_MODEL: "llama3.1:8b"
```

If you set `KE_LLM_KEY` you **must** also set `KE_LLM_BASE_URL`. The server refuses
otherwise, and says why: it attaches the key to whatever endpoint it is given, so
an endpoint chosen by the page would be a way to post your key somewhere else.

Two caveats for a hosted endpoint over https: the scratch image carries no root
certificates, so swap the final stage for alpine (there is a comment in
`Containerfile` showing how), and remember that what you send leaves your machine —
the Anonymise page stops being optional at that point.

## Tests

```bash
make test
```

Node and Python only. Nothing needs the app to be running.

## Generating a model with an AI

`prompts/generate-model.md` is the prompt. Paste it into a capable model, paste
your document after it, and import what comes back with **Knowledge models →
Import JSON**. `tools/test_import.js` checks that the prompt still asks for the
envelope this build accepts, so the instructions cannot quietly go stale.
