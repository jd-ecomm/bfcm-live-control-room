#!/usr/bin/env python3
"""Inject data/model.json into src/template.html -> out/index.html"""
import json
from pathlib import Path
R = Path(__file__).resolve().parent.parent
m = (R / 'data/model.json').read_text()
json.loads(m)
t = (R / 'src/template.html').read_text()
assert '/*__MODEL__*/' in t
(R / 'out').mkdir(exist_ok=True)
html = t.replace('/*__MODEL__*/', m.replace('</', '<\\/'))
if not html.lstrip().lower().startswith('<!doctype'):
    html = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"></head><body>\n' + html + '\n</body></html>'
(R / 'out/index.html').write_text(html)
print('built out/index.html', len(t) + len(m))
