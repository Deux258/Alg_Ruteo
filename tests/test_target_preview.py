"""Target preview stays independent of mission weather, solver locks and database writes."""
import io
import json
import unittest
from unittest.mock import patch

from shapely.geometry import box, mapping
from shapely.ops import transform

from core.aerial_data import FWD, INV
from core.web import Handler


class TargetPreviewTests(unittest.TestCase):
    def setUp(self):
        x, y = FWD(-71.65, -33.1)
        self.study = mapping(transform(INV, box(x-200, y-200, x+200, y+200)))
        self.target = mapping(transform(INV, box(x-40, y-40, x+40, y+40)))

    def invoke(self, target, display):
        handler = Handler.__new__(Handler)
        handler.path = '/api/aereo/patrullaje/objetivo'
        body = json.dumps(dict(target_polygon=target)).encode()
        handler.headers = {'Content-Length': str(len(body))}
        handler.rfile = io.BytesIO(body)
        responses = []
        handler.json_reply = lambda value, code=200: responses.append((code, value))
        handler.reply = lambda code, value: responses.append((code, json.loads(value)))
        with patch.dict('os.environ', {'PATROL_CONTEXT': 'fixture'}), \
             patch('core.web.patrol_model', return_value={'study_geometry': self.study}), \
             patch('core.web.connect', side_effect=AssertionError('Preview must not open a database here')), \
             patch('core.web.PATROL_LOCK') as lock, \
             patch('core.vertical_profile.target_display_summary', return_value=display) as helper:
            Handler.do_POST(handler)
            lock.acquire.assert_not_called()
        return responses, helper

    def test_preview_does_not_wait_for_routing_or_weather(self):
        display = dict(status='known', level_m_egm2008=130, offset_m=30,
                       polygon_sha256='polygon', terrain_sha256='terrain')
        responses, helper = self.invoke(self.target, display)
        self.assertEqual(responses, [(200, {'target_display': display})])
        helper.assert_called_once()
        self.assertEqual(helper.call_args.args[1]['type'], 'Polygon')

    def test_unknown_elevation_is_a_diagnostic_without_an_invented_level(self):
        display = dict(status='unknown_elevation', level_m_egm2008=None, offset_m=30)
        responses, _ = self.invoke(self.target, display)
        self.assertEqual(responses[0][0], 200)
        self.assertIsNone(responses[0][1]['target_display']['level_m_egm2008'])

    def test_outside_or_invalid_target_never_reaches_elevation_helper(self):
        for target in (mapping(box(0, 0, 1, 1)), {'type': 'Point', 'coordinates': [-71.65, -33.1]}):
            with self.subTest(target=target):
                responses, helper = self.invoke(target, {})
                self.assertEqual(responses[0][0], 422)
                helper.assert_not_called()
