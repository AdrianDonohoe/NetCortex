# impact diagrams

`impact-flow.{json,svg,png}` — the impact pipeline, end to end: the
read-only assess advisory, the human decision gate, and the annotation
loop that alone writes the Change History, whose failed records feed
back into the rubric.

## Regenerating

The SVG is generated from the IR by the fireworks-tech-graph skill
(style 2, dark terminal), following the same conventions as
[dispatch's pipeline diagram](../../../dispatch/docs/diagrams/README.md).

```bash
python3 scripts/fireworks.py render agent impact-flow.json impact-flow.svg
python3 scripts/fireworks.py check impact-flow.svg
python3 scripts/fireworks.py inspect impact-flow.svg
```

(run from this directory, with `scripts/` the
[fireworks-tech-graph](https://github.com/yizhiyanhua-ai/fireworks-tech-graph)
skill's script directory)

The PNG is exported with resvg-py (this VM has no system fonts or
Cairo, so cairosvg renders textless images) using the FiraCode 6.2
release fonts:

```bash
# once: fonts at /tmp/firacode/extracted/ttf/ (Fira_Code_v6.2.zip from
# https://github.com/tonsky/FiraCode/releases/tag/6.2) and
uv venv /tmp/diagram-venv && uv pip install --python /tmp/diagram-venv/bin/python resvg-py pillow
```

```python
import resvg_py
png = resvg_py.svg_to_bytes(
    svg_path="impact-flow.svg",
    width=1334,
    font_files=[
        "/tmp/firacode/extracted/ttf/FiraCode-Regular.ttf",
        "/tmp/firacode/extracted/ttf/FiraCode-Medium.ttf",
        "/tmp/firacode/extracted/ttf/FiraCode-SemiBold.ttf",
        "/tmp/firacode/extracted/ttf/FiraCode-Bold.ttf",
    ],
)
open("impact-flow.png", "wb").write(png)
```

A PNG can fail silently (text missing). Verify by cropping the title
band (y≈20–58) and asserting non-zero near-white pixels:

```python
from PIL import Image
img = Image.open("impact-flow.png").convert("RGB")
band = img.crop((0, 0, img.width, 80))
assert sum(1 for px in band.getdata() if all(c > 200 for c in px)) > 0
```
