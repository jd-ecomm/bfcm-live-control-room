# JD Black Friday Control Room

Live hourly BFCM dashboard for JD Sports Canada ecommerce. Published with GitHub Pages from `index.html` (Dashboard view: `#screen`).

Each hourly run pulls today's data into `data/`, then:

    python3 tools/compute.py      # data/*.json -> data/model.json
    python3 tools/build.py        # src/template.html + model -> out/index.html
    cp out/index.html index.html

Full source list and decisions: RUNBOOK.md.
