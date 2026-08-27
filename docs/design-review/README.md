# Visual design review — evidence captures

Captures backing the visual-design issue for the terminal shell. They exist so the
proposal can be judged against real rendering instead of a mockup.

All four images are unmodified `google-chrome --headless` captures of the dev server
(`.venv/bin/python deuscfo.py dev`, `http://127.0.0.1:3000`) at a 1280×760 viewport,
first run with no league saved, taken on `7dbff1c`.

| File | What it shows |
| --- | --- |
| `cfo-current.webp` | CFO tab as shipped |
| `cfo-proposed.webp` | Same view with `prototype.css` appended to `frontend/src/index.css` |
| `cfo-before-after.webp` | The two stacked for comparison |
| `oracle-lens-collision.webp` | Detail crop: the oracle lens printing over `MARKET STATE UNASSESSED` and the `Simulations` field, before and after |

`prototype.css` is the throwaway override used to produce the "proposed" capture. It is
not wired into the build and is not intended to be merged as-is; it exists so the
numbers in the issue (border contrast, type scale, spacing scale, button tiers,
decoration placement) can be reproduced in one step:

```bash
cat docs/design-review/prototype.css >> frontend/src/index.css   # Vite hot-reloads
# ... look at http://127.0.0.1:3000 ...
git checkout frontend/src/index.css                              # revert
```

Contrast ratios quoted in the issue are computed with the WCAG 2.1 relative-luminance
formula against `--bg: #0b0c0e`.
