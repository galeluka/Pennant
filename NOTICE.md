# NOTICE

Attribution obligations that travel with every distributed artefact — container
image, tarball, installer, and any hosted build that serves this code to a
browser. Keep this file in the repository root and include it in each of those.

## Unconditional: vendored third-party code

These obligations hold regardless of which licence you choose for your own code.
Both components are vendored under `web/vendor/` and served locally; neither is
fetched from the internet at runtime.

| Component | Version | Licence | What must travel |
|---|---|---|---|
| vis-network | 9.1.9 | Apache-2.0 or MIT | Copyright notice and full licence text. Apache-2.0 additionally requires that you state any modifications you made. |
| Font Awesome Free | 6.4.0 | CC BY 4.0 (icons) · SIL OFL 1.1 (fonts) · MIT (code) | Attribution for the icons; OFL requires the font's own licence to accompany it and reserves the name. |

Full texts are in `web/vendor/*.LICENSE*.txt` and `THIRD-PARTY-NOTICES.md`.
Getting this wrong is the most likely way to actually infringe something, and it
is unrelated to your own licensing decision.

## Conditional: your own code

Fill in whichever applies once §1 of `LAUNCH-LICENCE.md` is decided. Delete the
other two.

**If the community edition ships under AGPL-3.0** — a commercial build you
distribute under your own commercial licence needs no notice for your own code,
because you hold the copyright. But if a commercial build contains AGPL code you
do not solely own (any contribution merged without an assignment), that build
must comply with AGPL in full, including offering the corresponding source to
anyone it is served to over a network. See §2 of `LAUNCH-LICENCE.md`.

**If the community edition ships under BSL 1.1 or FSL** — the licence text, the
change date and the additional-use grant must travel with every copy. State the
change date explicitly; a BSL file without one is unusable by anyone reading it.

**If the community edition ships under MIT** — then a commercial build that
contains any of it must carry:

> Copyright (c) 2026 Luka Gale
>
> [full MIT licence text]

## Community-contributed templates

Nothing has been published yet, so there are no external contributions to
account for. If that changes, and contributions are accepted under a licence
without copyright assignment, those files cannot be relicensed and this file must
record them separately. Resolve the CLA before the repository goes public.
