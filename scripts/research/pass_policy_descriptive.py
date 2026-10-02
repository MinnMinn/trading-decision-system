"""DESCRIPTIVE add-on to pass_policy.py (post hoc, never used to choose): funded-within-122-days by start year, and two
accounts started 28 days apart. python3 scripts/research/pass_policy_descriptive.py"""
import importlib.util, json, datetime, collections, sys
import os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
spec=importlib.util.spec_from_file_location("pp",os.path.join(ROOT, "scripts", "research", "pass_policy.py"))
PP=importlib.util.module_from_spec(spec); spec.loader.exec_module(PP)
raw=PP.load_raw()
lo=max(min(t["entry_time"] for t in raw[c]) for c in raw)
raw={c:[t for t in v if t["entry_time"]>=lo] for c,v in raw.items()}
pols={"reference":dict(book="base3",risk=0.01,throttle="none",day_stop=None),
      "chosen":dict(book="base3+G9au",risk=0.01,throttle="dd3",day_stop=None)}
out={}
for name,p in pols.items():
    tr=PP.prepare(raw,PP.BOOKS[p["book"]])
    starts=list(PP.mondays(tr,"2000-01-01","2100-01-01"))
    res={s:PP.challenge(tr,s,p) for s in starts}
    by=collections.defaultdict(list)
    for s,r in res.items(): by[s.year].append(r["funded_days"] is not None and r["funded_days"]<=122)
    two=[]
    for s in starts:
        s2=s+datetime.timedelta(days=28)
        if s2 not in res: continue
        a=res[s]["funded_days"]; b=res[s2]["funded_days"]
        two.append((a is not None and a<=122) or (b is not None and b+28<=122))
    out[name]={"funded_le_122d_by_start_year":{y:round(sum(v)/len(v),3) for y,v in sorted(by.items())},
               "two_accounts_staggered_28d_any_funded_le_122d":round(sum(two)/len(two),3),
               "one_account_funded_le_122d":round(sum(r["funded_days"] is not None and r["funded_days"]<=122 for r in res.values())/len(res),3),
               "starts":len(starts)}
print(json.dumps(out,indent=1))
json.dump(out,open(os.path.join(ROOT, "docs", "audits", "2026-10-02-pass-policy-descriptive.json"),"w"),indent=1)
