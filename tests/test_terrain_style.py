import copy
import unittest
import numpy as np
from core.terrain_style import TerrainLighting, terrain_vertex_colors


class ContinuousTerrainLighting(unittest.TestCase):
    def test_original_geometry_palette_and_shared_clipped_vertex_colors(self):
        mesh=dict(width=2,height=2,x=[0,100],y=[0,100],elevations=[0,10,0,10])
        before=copy.deepcopy(mesh)
        points=np.array([[0,0,0],[50,25,5],[50,25,5],[100,100,10]],dtype=float)
        original=points.copy()
        colors=terrain_vertex_colors(mesh,points)
        shade=.68+.32*abs((.035+.87)/np.hypot(.1,1))
        expected=np.floor(np.array([.59,.63,.48])*shade*255+.5).astype(np.uint8)
        np.testing.assert_array_equal(colors[0],expected)
        np.testing.assert_array_equal(colors[1],colors[2])
        np.testing.assert_array_equal(points,original)
        self.assertEqual(mesh,before)
        category=TerrainLighting(mesh).colors(points,base_color=[.2,.5,.3])
        expected=np.floor(np.array([.2,.5,.3])*shade*255+.5).astype(np.uint8)
        np.testing.assert_array_equal(category[0],expected)
        np.testing.assert_array_equal(category[1],category[2])

    def test_nodata_faces_do_not_contribute_normals_or_mutate_unknowns(self):
        mesh=dict(width=2,height=2,x=[0,100],y=[0,100],elevations=[20,20,20,None])
        points=np.array([[0,0,20],[100,0,20],[0,100,20]])
        colors=terrain_vertex_colors(mesh,points)
        self.assertEqual(colors.dtype,np.uint8)
        np.testing.assert_array_equal(colors[0],colors[1])
        np.testing.assert_array_equal(colors[1],colors[2])
        self.assertIsNone(mesh['elevations'][-1])
        self.assertEqual(terrain_vertex_colors(mesh,[]).shape,(0,3))
