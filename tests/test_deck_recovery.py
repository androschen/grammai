"""Merge real card data across redirected folders without deleting source data."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from core.deck_recovery import recover_deck


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path.cwd());self.root=Path(self.temp.name)
        self.source=self.root/'cache'/'phrases.json';self.source.parent.mkdir()
        self.cards=[dict(id='a',native_text='original',target_text='meaning',notes='my note')]
        self.source.write_text(json.dumps(self.cards),encoding='utf8');self.target=self.root/'real'
    def tearDown(self):self.temp.cleanup()
    def recover(self,**kw):return recover_deck(self.target,[self.source],**kw)
    def test_recovers_missing_deck_keeps_source_and_is_idempotent(self):
        before=self.source.read_bytes();r=self.recover();self.assertEqual(r['recovered'],1)
        self.assertEqual(json.loads((self.target/'phrases.json').read_text()),self.cards)
        self.assertEqual(self.source.read_bytes(),before);self.assertEqual(self.recover()['recovered'],0)
    def test_preserves_newer_existing_card_and_backs_up_before_merge(self):
        self.target.mkdir();existing=[dict(self.cards[0],notes='Newer user note'),dict(id='b',native_text='second')]
        target=self.target/'phrases.json';target.write_text(json.dumps(existing),encoding='utf8')
        self.source.write_text(json.dumps(self.cards+[dict(id='c',notes='recover this')]),encoding='utf8')
        before=target.read_bytes();r=self.recover();merged=json.loads(target.read_text())
        self.assertEqual(merged[0]['notes'],'Newer user note');self.assertEqual(len(merged),3)
        self.assertEqual(Path(r['backup']).read_bytes(),before)
    def test_same_physical_path_and_dry_run_never_write(self):
        r=recover_deck(self.source.parent,[self.source]);self.assertEqual(r['recovered'],0)
        self.assertEqual(self.recover(dry_run=True)['recovered'],1);self.assertFalse(self.target.exists())
    def test_invalid_source_and_quota_failures_leave_target_unchanged(self):
        self.target.mkdir();target=self.target/'phrases.json';target.write_text('[]',encoding='utf8')
        with patch('core.deck_recovery.MAX_BYTES',1):
            with self.assertRaises(ValueError):self.recover()
        self.assertEqual(target.read_text(),'[]')
        self.source.write_text('invalid',encoding='utf8')
        with self.assertRaises(ValueError):self.recover()
        self.assertEqual(target.read_text(),'[]')
