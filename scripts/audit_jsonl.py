import json, pathlib
p = pathlib.Path(r'C:\Users\lenovo\Downloads\celesto-sandbox-agent\reports\failure_trace.jsonl')
ok=True
with open(p,'r',encoding='utf-8') as f:
    for i,line in enumerate(f,1):
        line=line.strip()
        if not line: continue
        try:
            json.loads(line)
        except Exception as e:
            print('Line',i,'FAIL',e)
            ok=False
if ok:
    print('failure_trace.jsonl OK')
