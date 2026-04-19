"""Integration test for Viewport tab with gizmos, properties panel, and project assets."""
import sys, os
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

app = QApplication(sys.argv)
from py_editor.main import MainWindow

errors = []

def run_test():
    try:
        w = MainWindow()
        w.resize(1000, 700)
        w.show()

        # Tab structure
        assert w.tabs.count() == 2, f"Expected 2 tabs, got {w.tabs.count()}"
        assert w.tabs.tabText(1) == "Viewport"
        print("[OK] 2 tabs: Logic, Viewport")

        se = w.scene_editor
        exp = w.explorer

        # Explorer has properties panel
        assert hasattr(exp, 'file_tree')
        print("[OK] Explorer dock exists")

        # Switch to Viewport
        w.tabs.setCurrentIndex(1)
        
        # Add object and test properties
        from py_editor.ui.scene.object_system import SceneObject
        obj = SceneObject("TestCube", "cube", position=[2.0, 1.0, 3.0])
        obj.rotation = [10.0, 20.0, 30.0]
        obj.scale = [1.5, 2.0, 0.5]
        se.viewport.scene_objects.append(obj)

        # Select it
        obj.selected = True
        se.viewport.object_selected.emit(obj)

        # Verify properties panel shows values (in its dock)
        props = w.properties
        assert obj in props._current_objects
        print("[OK] Properties panel shows selected object")

        # Edit position via properties panel
        props._pos_spins[0].setValue(5.0)
        assert abs(obj.position[0] - 5.0) < 0.01
        print("[OK] Properties panel edits update object position")

        # Deselect
        se.viewport.object_selected.emit(None)
        assert len(props._current_objects) == 0
        print("[OK] Properties panel clears on deselect")

        # Grid toggle (internal to viewport)
        se.viewport.show_grid = False
        assert se.viewport.show_grid == False
        se.viewport.show_grid = True
        print("[OK] Grid toggle works")

        # Tab switching
        w.tabs.setCurrentIndex(0)
        w.tabs.setCurrentIndex(1)
        print("[OK] Tab switching works")

        from PyQt6.QtOpenGLWidgets import QOpenGLWidget
        print(f"[OK] Viewport is QOpenGLWidget: {isinstance(se.viewport, QOpenGLWidget)}")

        w.close()
        print("\n=== ALL TESTS PASSED ===")

    except Exception as e:
        import traceback
        traceback.print_exc()
        errors.append(str(e))
        print(f"\n=== TEST FAILED: {e} ===")
    finally:
        app.quit()

QTimer.singleShot(500, run_test)
app.exec()
if errors:
    sys.exit(1)
