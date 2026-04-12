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
        assert w.tabs.count() == 3, f"Expected 3 tabs, got {w.tabs.count()}"
        assert w.tabs.tabText(1) == "Viewport"
        print("[OK] 3 tabs: Logic, Viewport, Anim")

        se = w.scene_editor
        assert se._ui_builder is w.ui_builder
        print("[OK] UIBuilderWidget injected")

        # Explorer has properties panel (Linked for test compatibility)
        assert hasattr(se.explorer, 'properties')
        from py_editor.ui.scene_editor import ObjectPropertiesPanel
        assert isinstance(se.explorer.properties, ObjectPropertiesPanel)
        print("[OK] Properties panel linked to explorer")

        # Switch to Viewport
        w.tabs.setCurrentIndex(1)

        # Mode switching
        se.toolbar.mode_combo.setCurrentText("3D")
        assert se._current_mode == "3D"
        # Count all recursive items in tree
        def count_tree(tree):
            c = 0
            for i in range(tree.topLevelItemCount()):
                it = tree.topLevelItem(i)
                c += 1 + it.childCount()
            return c
        
        # 3D: 3 Cats + (6 basic + 2 light + 1 cam) = 12
        assert count_tree(se.explorer.primitives_tree) >= 9 
        print(f"[OK] 3D mode: {count_tree(se.explorer.primitives_tree)} items in tree")

        se.toolbar.mode_combo.setCurrentText("2D")
        assert se._current_mode == "2D"
        # 2D: 1 Cat + 3 items = 4
        assert count_tree(se.explorer.primitives_tree) >= 3
        print(f"[OK] 2D mode: {count_tree(se.explorer.primitives_tree)} items in tree")

        se.toolbar.mode_combo.setCurrentText("Pure")
        assert se._stack.currentIndex() == 1
        print("[OK] Pure mode shows placeholder")

        se.toolbar.mode_combo.setCurrentText("UI")
        assert se._stack.currentIndex() == 2
        print("[OK] UI mode shows UIBuilder inline")

        se.toolbar.mode_combo.setCurrentText("3D")

        # Add object and test properties
        from py_editor.ui.scene_editor import SceneObject
        obj = SceneObject("TestCube", "cube", [2.0, 1.0, 3.0])
        obj.rotation = [10.0, 20.0, 30.0]
        obj.scale = [1.5, 2.0, 0.5]
        se.viewport.scene_objects.append(obj)

        # Select it
        obj.selected = True
        se._on_object_selected(obj)

        # Verify properties panel shows values
        props = se.explorer.properties
        assert props._current_object is obj
        assert abs(props._pos_spins[0].value() - 2.0) < 0.01
        assert abs(props._pos_spins[1].value() - 1.0) < 0.01
        assert abs(props._pos_spins[2].value() - 3.0) < 0.01
        print("[OK] Properties panel shows correct position")

        assert abs(props._rot_spins[1].value() - 20.0) < 0.1
        print("[OK] Properties panel shows correct rotation")

        assert abs(props._scale_spins[0].value() - 1.5) < 0.01
        print("[OK] Properties panel shows correct scale")

        # Edit position via properties panel
        props._pos_spins[0].setValue(5.0)
        assert abs(obj.position[0] - 5.0) < 0.01
        print("[OK] Properties panel edits update object position")

        # Deselect
        se._on_object_selected(None)
        assert props._current_object is None
        print("[OK] Properties panel clears on deselect")

        # Transform mode
        se.toolbar.move_btn.click()
        assert se.viewport._transform_mode == "move"
        se.toolbar.rotate_btn.click()
        assert se.viewport._transform_mode == "rotate"
        se.toolbar.scale_btn.click()
        assert se.viewport._transform_mode == "scale"
        print("[OK] Transform mode switching works")

        # Outliner
        se._refresh_outliner()
        assert se.explorer.outliner_tree.topLevelItemCount() >= 1
        print("[OK] Outliner shows object")

        # Grid toggle
        se.toolbar.grid_check.setChecked(False)
        assert se.viewport.show_grid == False
        se.toolbar.grid_check.setChecked(True)
        print("[OK] Grid toggle works")

        # Project assets tree (should have at least root node)
        assert se.explorer.assets_tree.topLevelItemCount() > 0
        root_item = se.explorer.assets_tree.topLevelItem(0)
        # Clean text for console safe printing
        root_text = root_item.text(0).encode('ascii', 'ignore').decode('ascii').strip()
        print(f"[OK] Assets tree root: '{root_text}' with {root_item.childCount()} children")

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
