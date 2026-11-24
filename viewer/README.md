# @soflution/simtrail

The [Simtrail](https://github.com/Soflutionltd/simtrail) viewer: a live iOS Simulator screen, a person's touches
and keys, and an AI agent's cursor, as a web component or a function.

```html
<sim-trail server="http://127.0.0.1:7466" scope="demo" token="…"></sim-trail>

<script type="module">
  import { defineSimtrailElement } from '@soflution/simtrail'
  defineSimtrailElement()
</script>
```

```ts
import { createHttpTransport, createViewer } from '@soflution/simtrail'

const view = createViewer(document.querySelector('#simulator')!, {
  transport: createHttpTransport({ baseUrl: 'http://127.0.0.1:7466', scope: 'demo', token: () => viewerToken }),
})
view.setActive(true)
```

- H.264 through WebCodecs where the page can decode it, JPEG otherwise.
- Touch, drag, scroll, typing, hardware buttons and appearance; a view-only mirror when the connector cannot touch.
- The agent's gestures drawn by the viewer's own cursor just before they land.
- The text read from the screen's pixels outlined over it, and what a box reads when pointed at.
- Themed with `--simtrail-*` custom properties and `::part()`; an ES module with types and no runtime dependencies.

It needs a Simtrail server: the `simtrail` daemon (`simtrail serve`), or a host application that mounts
Simtrail's routers.

Documentation:
[the web component and the viewer library](https://github.com/Soflutionltd/simtrail/blob/main/docs/embedding/web-component.md),
[getting started](https://github.com/Soflutionltd/simtrail/blob/main/docs/getting-started.md),
[security](https://github.com/Soflutionltd/simtrail/blob/main/docs/security.md).

Apache-2.0. Icons are from [Lucide](https://lucide.dev) (ISC).
