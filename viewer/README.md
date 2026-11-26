# @soflution/rocketwright

The [Rocketwright](https://github.com/Soflutionltd/rocketwright) viewer: a live iOS Simulator screen, a person's touches
and keys, and an AI agent's cursor, as a web component or a function.

```html
<rocket-wright server="http://127.0.0.1:7466" scope="demo" token="…"></rocket-wright>

<script type="module">
  import { defineRocketwrightElement } from '@soflution/rocketwright'
  defineRocketwrightElement()
</script>
```

```ts
import { createHttpTransport, createViewer } from '@soflution/rocketwright'

const view = createViewer(document.querySelector('#simulator')!, {
  transport: createHttpTransport({ baseUrl: 'http://127.0.0.1:7466', scope: 'demo', token: () => viewerToken }),
})
view.setActive(true)
```

- H.264 through WebCodecs where the page can decode it, JPEG otherwise.
- The device drawn in its own frame -- iPhone, iPad, Android -- at any zoom, with a floating toolbar, Edit, Device and
  View menus, the iOS Simulator's shortcuts, screenshots, and light and dark themes.
- Touch, drag, scroll, typing, hardware buttons and appearance; a view-only mirror when the connector cannot touch.
- The agent's gestures drawn by the viewer's own cursor just before they land.
- The text read from the screen's pixels outlined over it, and what a box reads when pointed at.
- In English, from one catalogue of messages that another language can be added to.
- Themed with `--rocketwright-*` custom properties and `::part()`; an ES module with types and no runtime dependencies.

It needs a Rocketwright server: the `rocketwright` daemon (`rocketwright serve`), or a host application that mounts
Rocketwright's routers.

## Languages

Everything the viewer says is a message in `src/locales/`, one file a language: `en.ts` is the reference and the
only one today. `t('zoom.level', { percent })` says one (`src/i18n.ts`), and TypeScript knows every key and the values each
message takes. To add a language:

1. Write `src/locales/<tag>.ts` -- `export const de: Messages = { … }` -- named by its BCP 47 primary subtag, with
   its own name under `language.name`. TypeScript names every key it lacks or invents.
2. Add it to `LOCALES` in `src/locales/index.ts`.

Nothing else changes: View > Language appears and lists it, `navigator.languages` and `lang` pick it, and the tests hold it to
English's keys and `{placeholders}`. A test also fails when text a person reads is written straight into a source file
instead of the catalogue (`src/hardcoded-text.test.ts`). Each language is about 3 KB of the bundle, gzipped, and
`make viewer-bundle` holds the bundle to its budget (45 KB): a second language needs room under it, or its catalogue
loaded on demand.

What the server says is not translated: a setting's and a section's description, a refusal's reason, a device's
name, what an agent says it is doing.

Documentation:
[the web component and the viewer library](https://github.com/Soflutionltd/rocketwright/blob/main/docs/embedding/web-component.md),
[getting started](https://github.com/Soflutionltd/rocketwright/blob/main/docs/getting-started.md),
[security](https://github.com/Soflutionltd/rocketwright/blob/main/docs/security.md).

Apache-2.0. Icons are from [Lucide](https://lucide.dev) (ISC).
