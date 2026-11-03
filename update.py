#!/usr/bin/env python3
"""Validate a reviewed upstream snapshot and stage a SourceList. Never deploys itself."""
import argparse,json,os,tempfile
from pathlib import Path
from urllib.parse import urlsplit

LIMITS={'sources':100,'liveSources':50}
def safe_url(value):
    if not isinstance(value,str): return False
    try:
        u=urlsplit(value)
        return u.scheme=='https' and bool(u.hostname) and not u.username and not u.password and not u.query and not u.fragment and u.port in (None,443) and not any(c in value for c in '\n\r\t')
    except ValueError: return False

def build(data, previous=None):
    if data.get('version')!=2: raise ValueError('unsupported version')
    out={'name':'自用源列表','version':2,'sources':[],'liveSources':[]}; seen=set()
    for group,limit in LIMITS.items():
        rows=data.get(group)
        if not isinstance(rows,list) or len(rows)>limit: raise ValueError('bad count: '+group)
        for item in rows:
            if not isinstance(item,dict) or not isinstance(item.get('name'),str) or not item['name'].strip() or not safe_url(item.get('url')): raise ValueError('unsafe entry: '+group)
            if item['url'] in seen: continue
            seen.add(item['url']); entry={'name':item['name'][:120], 'url':item['url']}
            if group=='sources': entry['isAdult']=bool(item.get('isAdult',False))
            for key in (('detail',) if group=='sources' else ('epg',)):
                if item.get(key):
                    if not safe_url(item[key]): raise ValueError('unsafe optional URL')
                    entry[key]=item[key]
            out[group].append(entry)
    if not out['sources'] and not out['liveSources']: raise ValueError('empty list')
    if previous:
        for group in LIMITS:
            old=previous.get(group,[])
            if old and len(out[group])*2 < len(old): raise ValueError('large drop: '+group)
        old_urls={x['url'] for group in LIMITS for x in previous.get(group,[])}
        new_urls={x['url'] for group in LIMITS for x in out[group]}
        if new_urls-old_urls: raise ValueError('new addresses require human review')
    return out

def main():
    p=argparse.ArgumentParser();p.add_argument('snapshot');p.add_argument('--previous');p.add_argument('--output',required=True);a=p.parse_args()
    data=json.loads(Path(a.snapshot).read_text()); old=json.loads(Path(a.previous).read_text()) if a.previous else None
    result=build(data,old); target=Path(a.output);target.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=target.parent,prefix='.stage-')
    try:
        with os.fdopen(fd,'w') as f: json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    print('staged',len(result['sources']),len(result['liveSources']))
if __name__=='__main__': main()
