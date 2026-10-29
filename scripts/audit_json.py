import json, pathlib
root = pathlib.Path(r'C:\Users\lenovo\Downloads\celesto-sandbox-agent\reports')
for p in sorted(root.glob('*.json')):
    try:
        data = json.load(open(p, 'r', encoding='utf-8'))
        print(p.name, 'OK', list(data.keys())[:5])
    except Exception as e:
        print(p.name, 'FAIL', e)
