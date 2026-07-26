# Contributing

## Before you open a pull request

```bash
node tools/smoke.js web/*.html   # every inline script must load
node tools/test_analyzers.js
node tools/test_llm_panel.js
node tools/test_landing.js
go vet ./... && gofmt -l . && go build ./...
```

`gofmt -l .` should print nothing.

## House style, such as it is

**Comments say why, not what.** The code already says what. A comment that survives
review explains a decision, names the failure it prevents, or records what was tried
and did not work. There is a lot of this in the existing source; match it.

**One HTML file, one inline `<script>`.** No build step, no bundler, no
`node_modules`. It is 7,000 lines and readable, and that is worth more than module
boundaries here.

**No third-party Go dependencies.** `go build` works offline against the standard
library. If you need a dependency, make the case in an issue first.

**Refuse rather than repair.** When a name, a setting or a file is wrong, say so and
stop. Silently rewriting what someone typed produces a workspace under a name they
did not choose, which is worse than an error message.

**An option that cannot work should not be offered.** Analyzers filter by what the
open model contains; so do lenses. If you add something selectable, decide what
makes it inapplicable and show that reason instead of hiding the option.

## Templates

See [`templates/README.md`](templates/README.md). Anonymise first, validate with
`tools/model-v2.py --check`, and confirm you have the right to publish it.

## Data safety

Never commit anything from a `data/` directory, a real document, or a model with a
customer, employee, supplier or hostname in it. `.gitignore` covers `/data/` but it
cannot cover a file you moved somewhere else first.
