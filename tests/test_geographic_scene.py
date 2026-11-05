import unittest

from shapely.geometry import Point, LineString, Polygon, box

from core.geographic_scene import (SceneSurface, coastal_water, contour_features,
                                   feature_height, geometry_from_osm, height_metres, scene_config)


class Base:
    source_sha256='fixture'
    def at(self,x,y):return 0.


def groups():return {k:[] for k in ('buildings','trees','water','landcover')}


class GeographicSceneTests(unittest.TestCase):
    def test_height_units_and_provenance(self):
        self.assertAlmostEqual(height_metres('30 ft'),9.144)
        self.assertEqual(height_metres('12,5 m'),12.5)
        self.assertIsNone(height_metres('12;20'))
        self.assertIsNone(height_metres('13 km'))
        self.assertEqual(feature_height({'height':'15'},'buildings',scene_config()),(15.,'osm:height',False))
        self.assertEqual(feature_height({'building:levels':'4'},'buildings',scene_config())[0],12)
        self.assertTrue(feature_height({},'trees',scene_config())[2])

    def test_multipolygon_preserves_courtyard_and_does_not_close_missing_rings(self):
        def member(points,role):return dict(type='way',role=role,geometry=[dict(lon=x,lat=y) for x,y in points])
        element=dict(type='relation',members=[member([(0,0),(10,0),(10,10)],'outer'),
            member([(10,10),(0,10),(0,0)],'outer'),member([(3,3),(7,3),(7,7),(3,7),(3,3)],'inner')])
        geom=geometry_from_osm(element)
        self.assertEqual(geom.area,84)
        self.assertFalse(geom.covers(Point(5,5)))
        element['members']=element['members'][:1]
        self.assertIsNone(geometry_from_osm(element))

    def test_narrow_building_is_sampled_and_occludes_sight(self):
        rows=groups();rows['buildings']=[dict(geometry=box(6,-3,8,3),properties=dict(id='tall',height_m=80))]
        surface=SceneSurface(Base(),rows,scene_config(),'test')
        self.assertEqual(surface.at(7,0),80)
        self.assertEqual(surface.at(4,0),0)
        self.assertTrue(any(.2<f<.267 for f in surface.fractions([0,0],[30,0])))
        self.assertFalse(surface.visible([0,0,60],[30,0,0]))
        self.assertTrue(surface.visible([0,0,100],[30,0,100]))

    def test_touching_obstacles_do_not_create_coincident_samples(self):
        rows=groups();rows['buildings']=[dict(geometry=box(6,-3,8,3),properties=dict(id='a',height_m=80)),
            dict(geometry=box(8+1e-10,-3,10,3),properties=dict(id='b',height_m=40))]
        surface=SceneSurface(Base(),rows,scene_config(),'test')
        fractions=surface.fractions([0,0],[30,0])
        self.assertTrue(all((b-a)*30>=.000099 for a,b in zip(fractions,fractions[1:])))
        self.assertFalse(surface.visible([0,0,60],[30,0,0]))

    def test_dsm_obstacle_height_is_not_added_twice(self):
        class ExistingBuilding(Base):
            def at(self,x,y):return 100. if abs(x)<10 and abs(y)<10 else 80.
        rows=groups();rows['buildings']=[dict(geometry=box(-3,-3,3,3),properties=dict(id='existing',height_m=10))]
        surface=SceneSurface(ExistingBuilding(),rows,scene_config(),'test')
        self.assertEqual(surface.at(0,0),100)

    def test_forest_canopy_follows_local_slope(self):
        class Slope(Base):
            def at(self,x,y):return float(x)
        rows=groups();rows['landcover']=[dict(geometry=box(0,-100,1000,100),properties=dict(id='forest',category='forest'))]
        surface=SceneSurface(Slope(),rows,scene_config(),'test')
        self.assertLess(surface.at(50,0),100)
        self.assertGreater(surface.at(900,0),800)

    def test_water_disallows_landing_and_preserves_islands(self):
        rows=groups();rows['water']=[dict(geometry=Polygon([(0,0),(10,0),(10,10),(0,10)],holes=[[(3,3),(7,3),(7,7),(3,7)]]),properties={})]
        surface=SceneSurface(Base(),rows,scene_config(),'test')
        self.assertFalse(surface.can_land(1,1))
        self.assertTrue(surface.can_land(5,5))
        self.assertTrue(surface.can_land(20,20))

    def test_coastline_water_is_on_right_only(self):
        rows=[dict(geometry=LineString([(5,0),(5,10)]),properties={})]
        water=coastal_water(rows,box(0,0,10,10))
        self.assertEqual(sum(g.area for g in water),50)
        self.assertTrue(any(g.covers(Point(8,5)) for g in water))
        self.assertFalse(any(g.covers(Point(2,5)) for g in water))

    def test_clipped_coastline_endpoints_are_noded_to_area_boundary(self):
        rows=[dict(geometry=LineString([(5,1e-10),(5,10-1e-10)]),properties={})]
        water=coastal_water(rows,box(0,0,10,10))
        self.assertAlmostEqual(sum(g.area for g in water),50)

    def test_contours_follow_plane_and_respect_nodata(self):
        mesh=dict(width=2,height=2,x=[0,40],y=[0,40],elevations=[0,40,0,40],origin_utm=[0,0])
        lines=contour_features(mesh,20)
        middle=[r for r in lines if r['properties']['elevation_m']==20]
        self.assertTrue(middle)
        self.assertTrue(all(abs(x-20)<1e-8 for r in middle for x,y in r['geometry'].coords))
        mesh['elevations']=[None,40,None,40]
        self.assertEqual(contour_features(mesh,20),[])


if __name__=='__main__':unittest.main()
