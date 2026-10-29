import tempfile,unittest,sqlite3,json
from pathlib import Path
from testsignal import Store,parse,html_report,csv_report

def xml(cases):return ('<testsuites><testsuite>'+cases+'</testsuite></testsuites>').encode()
def case(name,state='',time='1',extra=''):return f'<testcase classname="api" name="{name}" time="{time}" {extra}>{state}</testcase>'

class TestSignal(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'runs.db';self.s=Store(self.path)
 def tearDown(self):self.s.db.close();self.tmp.cleanup()
 def test_roundtrip_persistence(self):
  run=self.s.ingest('a',xml(case('ok')));other=Store(self.path)
  self.assertEqual(other.report(run)['counts']['passed'],1);other.db.close()
 def test_duplicate_import_idempotent(self):
  raw=xml(case('ok'));self.assertEqual(self.s.ingest('a',raw),self.s.ingest('a',raw))
 def test_duplicate_digest_new_label_rejected(self):
  raw=xml(case('ok'));self.s.ingest('a',raw)
  with self.assertRaises(ValueError):self.s.ingest('b',raw)
 def test_label_conflict_preserves_original(self):
  self.s.ingest('a',xml(case('ok')))
  with self.assertRaises(sqlite3.IntegrityError):self.s.ingest('a',xml(case('other')))
  self.assertEqual(self.s.db.execute('select count(*) from attempts').fetchone()[0],1)
 def test_validation_is_atomic(self):
  with self.assertRaises(ValueError):self.s.ingest('a',xml(case('ok')+case('',time='2')))
  self.assertEqual(self.s.db.execute('select count(*) from runs').fetchone()[0],0)
 def test_mixed_requires_actual_observed_fail_pass(self):
  r=self.s.report(self.s.ingest('a',xml(case('retry','<failure>timeout</failure>')+case('retry'))))
  self.assertEqual(r['counts']['mixed'],1);self.assertEqual(r['attempt_count'],2);self.assertTrue(r['cases'][0]['review_required'])
 def test_single_fail_not_called_flaky(self):
  r=self.s.report(self.s.ingest('a',xml(case('bad','<error>reset</error>'))));self.assertEqual(r['cases'][0]['result'],'failed')
 def test_skip_not_passed(self):self.assertEqual(parse(xml(case('skip','<skipped/>')))[0]['status'],'skipped')
 def test_status_attribute_failure(self):self.assertEqual(parse(xml(case('bad',extra='status="failed"')))[0]['status'],'failure')
 def test_contradictory_status(self):
  with self.assertRaises(ValueError):parse(xml(case('bad','<failure/>',extra='status="passed"')))
 def test_conflicting_children(self):
  with self.assertRaises(ValueError):parse(xml(case('bad','<failure/><skipped/>')))
 def test_unknown_status(self):
  with self.assertRaises(ValueError):parse(xml(case('bad',extra='status="interrupted"')))
 def test_invalid_duration(self):
  for n in ['NaN','inf','-1','oops']:
   with self.subTest(n=n),self.assertRaises(ValueError):parse(xml(case('bad',time=n)))
 def test_empty_report_not_success(self):
  with self.assertRaises(ValueError):parse(xml(''))
 def test_dtd_rejected(self):
  with self.assertRaises(ValueError):parse(b'<!DOCTYPE testsuite><testsuite/>')
 def test_bad_root_rejected(self):
  with self.assertRaises(ValueError):parse(b'<anything/>')
 def test_utf16_not_silently_accepted(self):
  with self.assertRaises((ValueError,UnicodeError)):parse('<!DOCTYPE testsuite><testsuite/>'.encode('utf-16'))
 def test_unknown_outcome_child_rejected(self):
  with self.assertRaises(ValueError):parse(xml(case('bad','<rerunFailure>failed</rerunFailure>')))
 def test_oversized_rejected(self):
  with self.assertRaises(ValueError):parse(b' '*8_000_001)
 def test_explicit_baseline_deltas_and_missing(self):
  a=self.s.ingest('base',xml(case('regress')+case('recover','<failure/>')+case('gone')))
  b=self.s.ingest('next',xml(case('regress','<failure/>')+case('recover')+case('new')))
  r=self.s.report(b,a);self.assertEqual([x['change'] for x in r['cases']],['regressed','recovered','new']);self.assertEqual(len(r['missing_from_current']),1)
 def test_unknown_baseline_rejected(self):
  a=self.s.ingest('a',xml(case('ok')))
  with self.assertRaises(ValueError):self.s.report(a,999)
 def test_same_baseline_rejected(self):
  a=self.s.ingest('a',xml(case('ok')))
  with self.assertRaises(ValueError):self.s.report(a,a)
 def test_html_escapes_diagnostics(self):
  a=self.s.ingest('a',xml(case('x','<failure>&lt;script&gt;alert(1)&lt;/script&gt;</failure>')))
  out=html_report(self.s.report(a));self.assertNotIn('<script>',out);self.assertIn('&lt;script&gt;',out)
 def test_csv_formula_neutralized(self):
  a=self.s.ingest('a',xml(case('=HYPERLINK(1)')));self.assertIn("'=HYPERLINK",csv_report(self.s.report(a)))
 def test_file_distinguishes_same_name(self):
  a=self.s.ingest('a',xml(case('same',extra='file="a.py"')+case('same',extra='file="b.py"')));self.assertEqual(len(self.s.report(a)['cases']),2)
 def test_raw_digest_binds_input(self):
  import hashlib
  raw=xml(case('ok'));a=self.s.ingest('a',raw);self.assertEqual(self.s.report(a)['run']['digest'],hashlib.sha256(raw).hexdigest())
if __name__=='__main__':unittest.main(verbosity=2)
