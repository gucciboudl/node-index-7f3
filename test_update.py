import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from update import build
class Tests(unittest.TestCase):
 def sample(self): return {'version':2,'sources':[{'name':'one','url':'https://example.org/api','isAdult':False}],'liveSources':[]}
 def test_valid(self): self.assertEqual(len(build(self.sample())['sources']),1)
 def test_secret_query(self):
  x=self.sample(); x['sources'][0]['url']+='?token=secret'
  with self.assertRaises(ValueError):build(x)
 def test_empty(self):
  with self.assertRaises(ValueError):build({'version':2,'sources':[],'liveSources':[]})
 def test_new_domain_requires_review(self):
  old=build(self.sample()); new=self.sample();new['sources'][0]['url']='https://other.example/api'
  with self.assertRaises(ValueError):build(new,old)
 def test_drop(self):
  old={'sources':[{'url':f'https://example.org/{i}'} for i in range(3)],'liveSources':[]}
  with self.assertRaises(ValueError):build(self.sample(),old)
if __name__=='__main__':unittest.main()
