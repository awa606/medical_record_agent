# Embedded PDF font

- `NotoSansSC-Regular.ttf`: subset of Noto Sans SC (variable `wght=400` instance), SIL Open Font License 1.1.
- Source: https://github.com/notofonts/noto-cjk (`Sans/Variable/TTF/Subset/NotoSansSC-VF.ttf`).
- Subset ranges: ASCII, Latin-1, general punctuation, U+2100–214F (℃), CJK punctuation, CJK Unified Ideographs, full-width forms.
- Purpose: make exported PDF text searchable/copyable without relying on viewer-installed CID fonts.
- License: see `OFL.txt`.

Regenerate:

```powershell
python - <<'PY'
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools import subset
# instantiate wght=400, then subset to the ranges above and save as NotoSansSC-Regular.ttf
PY
```
