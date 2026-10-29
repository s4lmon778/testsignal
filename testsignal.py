"""Import JUnit attempts and report evidence-backed quality signals."""
import argparse,csv,hashlib,html,io,json,math,sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

def parse(raw):
 if len(raw)>8_000_000:raise ValueError('Oversized XML')
 decoded=raw.decode('utf-8-sig')
 if '\x00' in decoded or '<!DOCTYPE' in decoded.upper() or '<!ENTITY' in decoded.upper():
  raise ValueError('Oversized or unsupported XML declaration')
 root=ET.fromstring(raw)
 if root.tag not in ('testsuite','testsuites'):raise ValueError('Expected JUnit testsuite(s)')
 rows=[]
 for case in root.iter('testcase'):
  name=case.get('name','').strip()
  if not name:raise ValueError('Test case name required')
  seconds=float(case.get('time','0'))
  if not math.isfinite(seconds) or seconds<0:raise ValueError('Invalid duration')
  states=[x for x in case if x.tag in ('failure','error','skipped')]
  if any(x.tag not in ('failure','error','skipped','properties','system-out','system-err') for x in case):raise ValueError('Unsupported testcase child; refusing to infer success')
  if len(states)>1:raise ValueError('Conflicting terminal results')
  declared=case.get('status','').lower()
  if declared not in ('','run','passed','failed','error','skipped','notrun'):
   raise ValueError('Unknown testcase status')
  state=states[0].tag if states else {'failed':'failure','error':'error','skipped':'skipped','notrun':'skipped'}.get(declared,'passed')
  if states and declared in ('passed','failed','error','skipped','notrun'):
   expected={'passed':'passed','failed':'failure','error':'error','skipped':'skipped','notrun':'skipped'}[declared]
   if expected!=state:raise ValueError('Status contradicts child result')
  msg=(' '.join(states[0].itertext())+' '+states[0].get('message','')).strip() if states else ''
  identity=[case.get('file',''),case.get('classname',''),name]
  rows.append(dict(key=json.dumps(identity,ensure_ascii=False),name=name,classname=identity[1],file=identity[0],status=state,seconds=seconds,message=msg))
 if not rows:raise ValueError('No test cases; refusing empty success report')
 return rows

class Store:
 def __init__(self,path):
  self.db=sqlite3.connect(path);self.db.row_factory=sqlite3.Row
  self.db.execute('PRAGMA foreign_keys=ON')
  self.db.executescript('''CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY,label TEXT UNIQUE NOT NULL,digest TEXT UNIQUE NOT NULL,raw BLOB NOT NULL);
  CREATE TABLE IF NOT EXISTS attempts(run_id INTEGER REFERENCES runs(id),ordinal INTEGER,key TEXT,name TEXT,classname TEXT,file TEXT,status TEXT,seconds REAL,message TEXT,PRIMARY KEY(run_id,ordinal));''')
 def ingest(self,label,raw):
  if not label.strip():raise ValueError('Run label required')
  rows=parse(raw);digest=hashlib.sha256(raw).hexdigest()
  with self.db:
   same=self.db.execute('SELECT id,label FROM runs WHERE digest=?',(digest,)).fetchone()
   if same:
    if same['label']!=label:raise ValueError('Identical report already imported under another label')
    return same['id']
   run=self.db.execute('INSERT INTO runs(label,digest,raw) VALUES(?,?,?)',(label,digest,raw)).lastrowid
   self.db.executemany('INSERT INTO attempts VALUES(?,?,?,?,?,?,?,?,?)',[(run,n,*[row[k] for k in ['key','name','classname','file','status','seconds','message']]) for n,row in enumerate(rows)])
  return run
 def report(self,run,baseline=None):
  meta=self.db.execute('SELECT id,label,digest FROM runs WHERE id=?',(run,)).fetchone()
  if not meta:raise ValueError('Unknown run')
  if baseline==run:raise ValueError('Baseline must be a distinct run')
  previous={x['key']:x for x in self.report(baseline)['cases']} if baseline is not None else {}
  grouped={}
  for row in self.db.execute('SELECT * FROM attempts WHERE run_id=? ORDER BY ordinal',(run,)):
   grouped.setdefault(row['key'],[]).append(dict(row))
  cases=[]
  for key,attempts in grouped.items():
   statuses={x['status'] for x in attempts};failed=bool(statuses&{'failure','error'})
   # Mixed outcomes are observed instability, never an inferred root cause.
   result='mixed' if failed and 'passed' in statuses else 'failed' if failed else 'passed' if 'passed' in statuses else 'skipped'
   old=previous.get(key)
   delta='uncompared' if baseline is None else 'new' if not old else 'regressed' if old['result']=='passed' and result in ('failed','mixed') else 'recovered' if old['result'] in ('failed','mixed') and result=='passed' else 'unchanged'
   cases.append(dict(key=key,name=attempts[0]['name'],classname=attempts[0]['classname'],file=attempts[0]['file'],result=result,change=delta,attempts=attempts,seconds=sum(x['seconds'] for x in attempts),review_required=result in ('failed','mixed')))
  removed=sorted(set(previous)-set(grouped)) if baseline is not None else []
  return dict(run=dict(meta),baseline=baseline,counts={s:sum(x['result']==s for x in cases) for s in ['passed','failed','mixed','skipped']},attempt_count=sum(len(x['attempts']) for x in cases),cases=cases,missing_from_current=removed,release_decision='Human review required; this report does not approve a release.')

def csv_report(report):
 stream=io.StringIO(newline='');out=csv.writer(stream)
 out.writerow(['class','name','result','change','attempts','seconds','review_required'])
 def safe(v):
  s=str(v);return "'"+s if s.lstrip().startswith(('=','+','-','@')) else s
 for row in report['cases']:out.writerow([safe(row['classname']),safe(row['name']),row['result'],row['change'],len(row['attempts']),row['seconds'],row['review_required']])
 return stream.getvalue()

def html_report(report):
 esc=lambda x:html.escape(str(x),quote=True)
 rows=[]
 for case in report['cases']:
  attempts=''.join('<li>'+esc(x['status'])+': '+esc(x['message'] or 'No diagnostic message')+'</li>' for x in case['attempts'])
  rows.append('<tr><td>'+esc(case['classname'])+'<br><b>'+esc(case['name'])+'</b></td><td>'+esc(case['result'])+'</td><td>'+esc(case['change'])+'</td><td>'+str(len(case['attempts']))+'</td><td>'+esc(round(case['seconds'],3))+'</td><td><details><summary>Attempt evidence</summary><ul>'+attempts+'</ul></details></td></tr>')
 return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>TestSignal report</title><style>body{font:16px system-ui;max-width:1100px;margin:40px auto;padding:0 20px;background:#f4f6fa;color:#162236}table{border-collapse:collapse;background:white;width:100%}td,th{padding:14px;border-bottom:1px solid #ccd4df;text-align:left;vertical-align:top}code{overflow-wrap:anywhere}summary{cursor:pointer}aside{padding:20px;background:#fff3cd}h1{font-size:36px}</style><h1>TestSignal</h1><p>Run '+esc(report['run']['label'])+' · '+str(report['attempt_count'])+' attempts</p><p>'+esc(report['counts'])+'</p><p>Source SHA-256: <code>'+esc(report['run']['digest'])+'</code></p><aside>'+esc(report['release_decision'])+' Mixed means both passing and failing attempts were observed for the same identity in this report. Missing baseline cases: '+str(len(report['missing_from_current']))+'.</aside><h2>Cases and changes</h2><table><thead><tr><th>Case</th><th>Result</th><th>Baseline change</th><th>Attempts</th><th>Seconds</th><th>Evidence</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></html>'

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--db',default='testsignal.sqlite3');sub=p.add_subparsers(dest='command',required=True)
 i=sub.add_parser('import');i.add_argument('label');i.add_argument('xml',type=Path)
 r=sub.add_parser('report');r.add_argument('run',type=int);r.add_argument('--baseline',type=int);r.add_argument('--out',type=Path,default=Path('report'))
 a=p.parse_args();s=Store(a.db)
 if a.command=='import':print(s.ingest(a.label,a.xml.read_bytes()))
 else:
  d=s.report(a.run,a.baseline);a.out.mkdir(parents=True,exist_ok=True)
  (a.out/'report.json').write_text(json.dumps(d,indent=2),encoding='utf8')
  (a.out/'report.csv').write_text(csv_report(d),encoding='utf8')
  (a.out/'index.html').write_text(html_report(d),encoding='utf8');print(json.dumps(d['counts']))
if __name__=='__main__':main()
