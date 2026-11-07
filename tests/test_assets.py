import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core.assets import resolve_asset
from core.contracts import ROOT, sha256


class AssetStoreTests(unittest.TestCase):
    def test_all_preserved_aliases_have_exact_original_digest(self):
        aliases=json.loads((ROOT/'config/asset_aliases.json').read_text())
        for name,digest in aliases.items():
            with self.subTest(name=name):
                self.assertEqual(sha256(ROOT/'datos/entrada/blobs'/digest),digest)
                self.assertEqual(sha256(resolve_asset(ROOT/name,digest)),digest)

    def test_alias_fallback_rejects_corrupted_content_and_unknown_names(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve();(root/'config').mkdir();(root/'datos/entrada/blobs').mkdir(parents=True)
            data=root/'datos/entrada/blobs'/('a'*64);data.write_bytes(b'corrupted')
            (root/'config/asset_aliases.json').write_text(json.dumps({'original.tif':'a'*64}))
            with patch('core.assets.ROOT',root):
                with self.assertRaisesRegex(ValueError,'Original alterado'):resolve_asset(root/'original.tif')
                with self.assertRaises(FileNotFoundError):resolve_asset(root/'missing.tif')
                with self.assertRaises(FileNotFoundError):resolve_asset(root.parent/'outside.tif')
