import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from check import unpack_gist,probe,public_addresses
class Tests(unittest.TestCase):
 def test_gist(self):
  payload={'files':{'libretv-sources.json':{'content':json.dumps({'version':2,'sources':[],'liveSources':[]})}}}
  self.assertEqual(unpack_gist(json.dumps(payload).encode())['version'],2)
 def test_truncated(self):
  with self.assertRaises(ValueError):unpack_gist(b'{"files":{"libretv-sources.json":{"truncated":true}}}')
 @patch('check.get',return_value=b'{"list":[]}')
 def test_search(self,unused): self.assertEqual(probe({'url':'https://example.org/api'},'sources'),'search_response')
 @patch('check.get',side_effect=TimeoutError())
 def test_timeout_unknown(self,unused): self.assertEqual(probe({'url':'https://example.org/api'},'sources'),'unknown')
 @patch('check.socket.getaddrinfo',return_value=[(0,0,0,'',('127.0.0.1',443))])
 def test_private_rejected(self,unused):
  with self.assertRaises(ValueError):public_addresses('example.org')
if __name__=='__main__':unittest.main()

class MergeTests(unittest.TestCase):
 def pair(self):
  old={'version':2,'sources':[{'name':'one','url':'https://example.org/old'}],'liveSources':[]}
  new={'version':2,'sources':[{'name':'one','url':'https://example.org/new'}],'liveSources':[]}
  return old,new
 def test_accept_same_host_only_when_probe_passes(self):
  from check import merge_reviewed
  old,new=self.pair(); result,events=merge_reviewed(new,old,lambda e,g:'search_response')
  self.assertEqual(result['sources'][0]['url'],'https://example.org/new')
 def test_failed_probe_retains_old(self):
  from check import merge_reviewed
  old,new=self.pair(); result,events=merge_reviewed(new,old,lambda e,g:'unknown')
  self.assertEqual(result['sources'][0]['url'],'https://example.org/old')
 def test_domain_move_requires_review(self):
  from check import merge_reviewed
  old,new=self.pair();new['sources'][0]['url']='https://other.example/new'
  result,events=merge_reviewed(new,old,lambda e,g:'search_response')
  self.assertEqual(result['sources'][0]['url'],'https://example.org/old');self.assertEqual(events[0]['state'],'domain_change_review')

class LiveAliasTests(unittest.TestCase):
 def test_alias_same_host_verified(self):
  from check import merge_reviewed
  old={'version':2,'sources':[], 'liveSources':[{'name':'zbds IPTV4','url':'https://example.org/old'}]}
  incoming={'version':2,'sources':[], 'liveSources':[{'name':'zbds IPTV4 (521台·带台标EPG)','url':'https://example.org/new'}]}
  result,events=merge_reviewed(incoming,old,lambda e,g:'playlist_response')
  self.assertEqual(result['liveSources'][0]['url'],'https://example.org/new')
  self.assertEqual(result['liveSources'][0]['name'],'zbds IPTV4')
  self.assertEqual([e['state'] for e in events],['same_host_update'])
 def test_alias_domain_change_retained(self):
  from check import merge_reviewed
  old={'version':2,'sources':[], 'liveSources':[{'name':'zbds IPTV4','url':'https://example.org/old'}]}
  incoming={'version':2,'sources':[], 'liveSources':[{'name':'zbds IPTV4 (521台·带台标EPG)','url':'https://other.org/new'}]}
  result,events=merge_reviewed(incoming,old,lambda e,g:'playlist_response')
  self.assertEqual(result['liveSources'][0]['url'],'https://example.org/old')
  self.assertEqual([e['state'] for e in events],['domain_change_review'])
 def test_unknown_name_not_guessed(self):
  from check import merge_reviewed
  old={'version':2,'sources':[], 'liveSources':[{'name':'zbds IPTV4','url':'https://example.org/old'}]}
  incoming={'version':2,'sources':[], 'liveSources':[{'name':'zbds IPTV4 new','url':'https://example.org/new'}]}
  result,events=merge_reviewed(incoming,old,lambda e,g:'playlist_response')
  self.assertEqual(result['liveSources'][0]['url'],'https://example.org/old')
  self.assertEqual({e['state'] for e in events},{'missing_retained','new_source_review'})
