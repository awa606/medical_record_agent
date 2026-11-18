"""Package this fixed ESM prototype as a double-clickable offline HTML file."""
import base64
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent


def module(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    exports = re.findall(r"^export (?:const|function) (\w+)", text, re.M)
    text = re.sub(r"^import .*?;\s*", "", text, flags=re.M)
    text = re.sub(r"^export (?=const |function )", "", text, flags=re.M)
    return text, exports


model, model_exports = module("model.mjs")
capture, capture_exports = module("capture.mjs")
app = (ROOT / "app.mjs").read_text(encoding="utf-8")
app = re.sub(r"^import \{(.*?)\} from './model.mjs';", r"const {\1}=model;", app, flags=re.M)
app = re.sub(r"^import \{(.*?)\} from './capture.mjs';", r"const {\1}=capture;", app, flags=re.M)
icon = "data:image/png;base64," + base64.b64encode((ROOT / "assets/medilisten.png").read_bytes()).decode()
app = app.replace("./assets/medilisten.png", icon)
script = "const model=(()=>{\n" + model + "\nreturn {" + ",".join(model_exports) + "};})();\n"
script += "const capture=(({CASES,FIELD_DEFS})=>{\n" + capture + "\nreturn {" + ",".join(capture_exports) + "};})(model);\n"
script += app
assert "import " not in script, "Unexpected external dependency"
assert "</script" not in script.lower(), "Unexpected HTML delimiter"
html = (ROOT / "index.html").read_text(encoding="utf-8")
html = html.replace('<link rel="stylesheet" href="./style.css">', "<style>" + (ROOT / "style.css").read_text(encoding="utf-8") + "</style>")
html = html.replace('./assets/medilisten.png', icon)
html = html.replace('<script type="module" src="./app.mjs"></script>', '<script type="module">' + script + '</script>')
target = ROOT / "直接打开工作台.html"
target.write_text(html, encoding="utf-8")
print(f"Created {target.name}: {target.stat().st_size} bytes")
