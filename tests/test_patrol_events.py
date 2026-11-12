import math
import unittest

from core.patrol_events import arrival, baseline, probability, uniform


class FireBaselineTests(unittest.TestCase):
    def test_observed_count_and_exposure_are_not_a_user_percentage(self):
        b=baseline()
        self.assertEqual(b['count'],575)
        self.assertEqual(b['observation_days'],335)
        self.assertAlmostEqual(b['rate_per_km2_day'],575/(335*16396.1))
        self.assertTrue(b['sources'][0]['url'].startswith('https://www.conaf.cl/'))
        self.assertEqual(probability(0,100),0)
        self.assertEqual(probability(100,0),0)
        # Short sector flights must remain rare, not artificially inflated.
        self.assertLess(probability(160000,1200),.000001)
        self.assertAlmostEqual(probability(1e6,86400),-math.expm1(-b['rate_per_km2_day']))

    def test_invalid_exposure(self):
        for area,seconds in [(-1,2),(1,-1),(math.inf,1),(1,math.nan)]:
            with self.assertRaises(ValueError): probability(area,seconds)

    def test_reproducible_arrival_and_common_clock_for_different_horizons(self):
        a=arrival(42,3,1e12,10,86400)
        b=arrival(42,3,1e12,10,172800)
        self.assertEqual(a['appeared_at_s'],b['appeared_at_s'])
        self.assertEqual(a,arrival(42,3,1e12,10,86400))
        self.assertNotEqual(a['draw'],arrival(42,4,1e12,10,86400)['draw'])
        self.assertTrue(10<=a['appeared_at_s']<=86410)

    def test_uniform_draws_and_empirical_poisson_frequency(self):
        area=1e10;seconds=86400;expected=probability(area,seconds)
        draws=[uniform(seed,0,'arrival') for seed in range(2000)]
        self.assertTrue(all(0<=v<1 for v in draws))
        observed=sum(arrival(seed,0,area,0,seconds)['occurs'] for seed in range(2000))/2000
        self.assertLess(abs(observed-expected),.04)


if __name__=='__main__': unittest.main()
