import unittest
from py_editor.ui.scene_editor import SceneObject
from py_editor.ui.procedural_system import sample_height, get_biome_at

class TestLandscapeLogic(unittest.TestCase):
    def test_layered_noise(self):
        obj = SceneObject("TestLand", "landscape", [0,0,0], [0,0,0], [1,1,1])
        obj.landscape_type = 'procedural'
        obj.landscape_noise_layers = [
            {'amp': 10.0, 'freq': 0.1, 'octaves': 1},
            {'amp': 2.0, 'freq': 1.0, 'octaves': 3}
        ]
        
        h1 = sample_height(0.5, 0.5, obj)
        h2 = sample_height(10.7, 10.3, obj)
        print(f"Heights: {h1}, {h2}")
        self.assertNotEqual(h1, h2)
        
    def test_biomes(self):
        obj = SceneObject("TestBiomes", "landscape", [0,0,0], [0,0,0], [1,1,1])
        obj.landscape_biomes = [
            {
                'name': 'Lowland',
                'height_range': [-10.0, 5.0],
                'slope_range': [0.0, 1.0],
                'color': [0, 1, 0, 1],
                'spawns': []
            },
            {
                'name': 'Highland',
                'height_range': [5.0, 20.0],
                'slope_range': [0.0, 1.0],
                'color': [1, 1, 1, 1],
                'spawns': []
            }
        ]
        
        b1 = get_biome_at(obj, 2.0, 0.1, 0.0, 0.0)
        b2 = get_biome_at(obj, 10.0, 0.1, 0.0, 0.0)
        
        self.assertEqual(b1['name'], 'Lowland')
        self.assertEqual(b2['name'], 'Highland')
        print(f"Biomes: {b1['name']}, {b2['name']}")

if __name__ == '__main__':
    unittest.main()
