# Third-party notices

Both are vendored into `web/vendor/` and served from the same container. Nothing on
any page is fetched from an external network at runtime.

There are no third-party **Go** dependencies. `go build` works offline, against the
standard library only.

## vis-network 9.1.9

Graph canvas on the Structure page. Dual licensed Apache-2.0 or MIT, at your
option. Copyright (c) 2014-2017 Almende B.V. and contributors; (c) 2017-2019 vis.js
contributors. https://github.com/visjs/vis-network

## Font Awesome Free 6.4.0

Interface icons. Icons CC BY 4.0, fonts SIL OFL 1.1, code MIT.
Copyright (c) Fonticons, Inc. https://fontawesome.com/license/free

## What is actually in web/vendor/

```
vis-network.min.js                  466 kB, unmodified
vis-network.LICENSE-MIT.txt         from the published package
vis-network.LICENSE-APACHE-2.0.txt  from the published package
fontawesome.min.css                 100 kB, MODIFIED - see below
fontawesome.LICENSE.txt             from the published package
webfonts/fa-solid-900.woff2         147 kB
webfonts/fa-regular-400.woff2        25 kB
webfonts/fa-brands-400.woff2        106 kB
```

Both were taken from the published npm packages (`vis-network@9.1.9`,
`@fortawesome/fontawesome-free@6.4.0`) and their licence files came with them.

`fontawesome.min.css` is modified in two ways, and only these two: the font URLs
were rewritten from `../webfonts/` to `webfonts/`, because the file sits in
`web/vendor/` rather than in a `css/` directory, and the `.ttf` fallbacks were
removed because every browser that can run this app reads woff2. The header comment
in the file says the same thing. No selector, glyph or licence text is altered.

The `.ttf` and `fa-v4compatibility` files from the package are not shipped.
