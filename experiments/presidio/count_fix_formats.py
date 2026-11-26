"""How often does a batch use the situations the fixes were about? Counts only."""
import json,re,sys
from pathlib import Path
d=Path(sys.argv[1])
L=[json.loads(l) for l in open(d/'lines.jsonl',encoding='utf-8') if l.strip()]
X=[json.loads(l) for l in open(d/'files.jsonl',encoding='utf-8') if l.strip()]
vals=[(None,c['line']) for c in L]+[(k.split('.')[-1] if c['fmt']=='json' else k, str(v)) for c in X for r in c['records'] for k,v in r['fields'].items()]
print('lowercase h.no / hno:', sum(bool(re.search(r'(?<![A-Za-z])(?:h\. ?no|h[-/]no|hno)(?![A-Za-z])',v)) for _,v in vals))
print('r/o (any case):', sum(bool(re.search(r'(?i)(?<![A-Za-z])r/o(?![A-Za-z])',v)) for _,v in vals))
print('cells under a header with a pin word that hold a comma and other words:', sum(bool(k and re.search(r'(?i)pin|postal|पिन',k) and ',' in v and re.search(r'\d{6}',v) and re.search(r'[A-Za-zऀ-ॿ]{3}',v)) for k,v in vals))
print('cells under a header mixing patient with ward or bed:', sum(bool(k and re.search(r'(?i)bed|ward',k) and re.search(r'(?i)patient|pt|rogi|mareez',k)) for k,v in vals))
print('values starting with a bed/ward number:', sum(bool(re.match(r'\s*(?i:bed|cot|room|ward)\b.{0,6}\d',v)) for k,v in vals if k))
