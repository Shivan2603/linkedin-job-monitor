import json, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
logs = json.load(open('data/logs.json', encoding='utf-8'))
for l in logs[-40:]:
    msg = l['message'].encode('ascii', 'replace').decode()
    print("[{}] [{:7s}] [{:15s}] {}".format(l['ts'][11:19], l['level'], l['site'], msg[:100]))
