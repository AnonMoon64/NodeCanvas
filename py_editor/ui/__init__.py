"""UI components for NodeCanvas editor."""

from .canvas import LogicEditor, CanvasView, NodeItem, ConnectionItem  # CanvasView is alias for LogicEditor
from .node_editor import NodeEditorDialog
from .composite_editor import CompositeEditorDialog
from .node_settings import NodeSettingsDialog
from .codegen import CodeGenDialog
from .ui_builder import UIBuilderWidget, WidgetPaletteWidget, PropertyEditor, ScreenListWidget, WidgetListWidget
from .scene_editor import SceneEditorWidget, SceneExplorerPanel, ObjectPropertiesPanel

__all__ = [
    # Primary export
    'LogicEditor',
    # Backward compatibility alias
    'CanvasView',
    # Other components
    'NodeItem',
    'ConnectionItem',
    'NodeEditorDialog',
    'CompositeEditorDialog',
    'NodeSettingsDialog',
    'CodeGenDialog',
    'UIBuilderWidget',
    'WidgetPaletteWidget',
    'PropertyEditor',
    'ScreenListWidget',
    'WidgetListWidget',
    'SceneEditorWidget',
    'SceneExplorerPanel',
    'ObjectPropertiesPanel',
]
