#!/usr/bin/env python3
"""Fixed Gist read and conservative endpoint observations; never publishes."""
import argparse,http.client,ipaddress,json,socket,ssl
from pathlib import Path
from urllib.parse import urlsplit, urlencode
from update import build, safe_url
import os,tempfile,signal
GIST_HOST='api.github.com'
GIST_PATH='/gists/dbb7af044d90b5f51c1f32d0e0a200f6'
MAX_BODY=2_000_000
# Explicitly reviewed identity aliases from the fixed upstream snapshot. Unknown
# names remain pending review rather than being guessed from fuzzy similarity.
LIVE_ALIASES = {
 '4K专区（上游标注，未验证）': '★4K专区 (3台·ffmpeg实测3840x2160)',
 'zbds IPTV4': 'zbds IPTV4 (521台·带台标EPG)',
 'vbskycn IPTV4': 'vbskycn IPTV4 (6小时自动更新)',
 'iptv-org 中国大陆': 'iptv-org 中国大陆 (507台·含4K条目)',
 'YanG 综合源': 'YanG 综合源 (123台)',
}
class PinnedHTTPS(http.client.HTTPSConnection):
 def __init__(self,host,ip):
  super().__init__(host,443,timeout=8,context=ssl.create_default_context()); self.ip=ip
 def connect(self):
  sock=socket.create_connection((self.ip,443),self.timeout)
  self.sock=self._context.wrap_socket(sock,server_hostname=self.host)
def public_addresses(host):
 ips={r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)}
 if not ips or any(not ipaddress.ip_address(x).is_global for x in ips): raise ValueError('non-public destination')
 return sorted(ips)
def get(host,path):
 # A socket timeout alone does not bound slow streaming responses or DNS.
 # The GitHub runner is Linux; abort each complete request after 12 seconds.
 def expired(signum, frame): raise TimeoutError('request deadline exceeded')
 previous = signal.signal(signal.SIGALRM, expired)
 signal.setitimer(signal.ITIMER_REAL, 12)
 try:
  return _get(host,path)
 finally:
  signal.setitimer(signal.ITIMER_REAL, 0)
  signal.signal(signal.SIGALRM, previous)
def _get(host,path):
 conn=PinnedHTTPS(host,public_addresses(host)[0])
 try:
  conn.request('GET',path,headers={'User-Agent':'libretv-subscription-check/1','Accept':'application/json, application/vnd.apple.mpegurl, text/plain;q=0.9'})
  response=conn.getresponse()
  if 300<=response.status<400: raise ValueError('redirect refused')
  if response.status!=200: raise ValueError(f'HTTP {response.status}')
  body=response.read(MAX_BODY+1)
  if len(body)>MAX_BODY: raise ValueError('response too large')
  return body
 finally: conn.close()
def unpack_gist(payload):
 obj=json.loads(payload); f=obj.get('files',{}).get('libretv-sources.json',{})
 if f.get('truncated') or not isinstance(f.get('content'),str): raise ValueError('missing or truncated content')
 return json.loads(f['content'])
def fetch_upstream(): return unpack_gist(get(GIST_HOST,GIST_PATH))
def probe(entry,group):
 u=urlsplit(entry['url']); path=u.path or '/'
 if group=='sources': path+='?'+urlencode({'ac':'videolist','wd':'test'})
 try:
  body=get(u.hostname,path)
  if group=='sources':
   val=json.loads(body)
   if not isinstance(val,dict) or 'list' not in val or (val['list'] is not None and not isinstance(val['list'],list)): return 'invalid_response'
   return 'search_response'
  return 'playlist_response' if body.lstrip().startswith(b'#EXTM3U') else 'invalid_response'
 except (OSError,ValueError,json.JSONDecodeError,ssl.SSLError,http.client.HTTPException): return 'unknown'

def merge_reviewed(incoming,old,probe_fn=probe):
    """Accept same-name same-host path changes only after functional probe.

    Domain migrations remain pending review; missing/failed upstream retains old.
    """
    new=build(incoming); result={'name':'自用源列表','version':2,'sources':[],'liveSources':[]}; events=[]
    for group in ('sources','liveSources'):
        proposed={x['name']:x for x in new[group]}
        if len(proposed)!=len(new[group]): raise ValueError('ambiguous duplicate name')
        oldnames={x['name'] for x in old.get(group,[])}
        identities={name:(LIVE_ALIASES.get(name,name) if group=='liveSources' else name) for name in oldnames}
        if len(set(identities.values()))!=len(identities): raise ValueError('ambiguous alias')
        for original in old.get(group,[]):
            match=proposed.get(identities[original['name']]); chosen=original
            if match and match['url']!=original['url']:
                previous=urlsplit(original['url']); candidate=urlsplit(match['url'])
                if previous.hostname==candidate.hostname and safe_url(match['url']):
                    status=probe_fn(match,group)
                    expected='search_response' if group=='sources' else 'playlist_response'
                    if status==expected: chosen={**match, 'name':original['name']}; events.append({'name':original['name'],'state':'same_host_update'})
                    else: events.append({'name':original['name'],'state':'update_probe_failed'})
                else: events.append({'name':original['name'],'state':'domain_change_review'})
            if not match: events.append({'name':original['name'],'state':'missing_retained'})
            result[group].append(chosen)
        for name in proposed.keys()-set(identities.values()): events.append({'name':name,'state':'new_source_review'})
    return build(result),events

def main():
 p=argparse.ArgumentParser();p.add_argument('--previous',required=True);p.add_argument('--out',required=True);p.add_argument('--health',required=True);a=p.parse_args()
 if len({Path(a.previous).resolve(),Path(a.out).resolve(),Path(a.health).resolve()}) != 3: raise ValueError('paths must be distinct')
 old=json.loads(Path(a.previous).read_text()); incoming=fetch_upstream(); candidate,changes=merge_reviewed(incoming,old)
 health=[{'upstream_changes':changes}]
 for group in ('sources','liveSources'):
  for entry in candidate[group]: health.append({'name':entry['name'],'kind':group,'status':probe(entry,group)})
 # Stage only after all input has passed validation; published previous is never written.
 for name,value in ((a.out,candidate),(a.health,health)):
  target=Path(name); fd,tmp=tempfile.mkstemp(dir=target.parent,prefix='.stage-')
  try:
   with os.fdopen(fd,'w') as f: json.dump(value,f,ensure_ascii=False,indent=2); f.write('\n')
   os.replace(tmp,target)
  finally:
   if os.path.exists(tmp): os.unlink(tmp)
 print('candidate staged; playback and resolution not tested')
if __name__=='__main__': main()
