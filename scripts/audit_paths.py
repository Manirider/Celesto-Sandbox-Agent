import json, pathlib
root = pathlib.Path(r'C:\Users\lenovo\Downloads\celesto-sandbox-agent')
reports = {
    'containment.json': ['attack','blocked','host_untouched','evidence_paths','status'],
}
for fname in ['containment.json','reliability.json','lifecycle.json']:
    p = root/'reports'/fname
    data = json.load(open(p))
    if 'evidence_paths' in data:
        for epath in data.get('evidence_paths',[]):
            full = root/epath
            print(fname, epath, 'exists' if full.exists() else 'MISSING')
