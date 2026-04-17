import json
from pathlib import Path
import zipfile
import tempfile

ROOT = Path(__file__).resolve().parent.parent  # Go up to py_editor/ directory
NODES_DIR = ROOT / "nodes"
BASE_DIR = NODES_DIR / "base"
CORE_DIR = NODES_DIR / "core"  # Core nodes like LogicReference, InterfaceInput, InterfaceOutput
ANIMATION_DIR = NODES_DIR / "animation"  # Animation nodes like Play, Stop, Blend
COMPOSITE_DIR = NODES_DIR / "composite"
GRAPHS_DIR = NODES_DIR / "graphs"
PLUGINS_DIR = ROOT / "plugins"  # Plugin directory for user extensions

PARTICLES_DIR = NODES_DIR / "particles"

for d in (NODES_DIR, BASE_DIR, CORE_DIR, ANIMATION_DIR, COMPOSITE_DIR, GRAPHS_DIR, PLUGINS_DIR, PARTICLES_DIR):
    d.mkdir(parents=True, exist_ok=True)

# in-memory registry: name -> data (includes 'type' key and '__path')
_templates = {}

# Track plugin packages for UI display
_plugin_packages = {}  # package_name -> {'path': str, 'nodes': [node_names]}

# Track plugin Python modules
_plugin_modules = {}  # package_name -> loaded module object

# Cache directory for extracted plugin modules
PLUGIN_CACHE_DIR = ROOT / ".plugin_cache"
PLUGIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def _normalize_io_format(data):
    """Normalize inputs/outputs from dict format to simple string format.
    Converts {"pin": {"type": "float"}} to {"pin": "float"}
    
    IMPORTANT: Skip normalization for composite templates - they need the full
    dict format with node/pin info for execution mapping.
    """
    # Don't normalize composite templates - they need full dict format
    if data.get('type') == 'composite':
        return data
    
    for key in ['inputs', 'outputs']:
        if key in data and isinstance(data[key], dict):
            normalized = {}
            for pin_name, pin_spec in data[key].items():
                if isinstance(pin_spec, dict) and 'type' in pin_spec:
                    normalized[pin_name] = pin_spec['type']
                elif isinstance(pin_spec, str):
                    normalized[pin_name] = pin_spec
                else:
                    normalized[pin_name] = 'any'
            data[key] = normalized
    return data

def _load_from_dir(dpath: Path, ttype='base'):
    global _templates
    for p in dpath.glob("*.json"):
        try:
            with p.open('r', encoding='utf-8') as f:
                data = json.load(f)
                name = data.get('name') or p.stem
                data.setdefault('type', ttype)
                data['__path'] = str(p)
                data = _normalize_io_format(data)
                _templates[name] = data
        except Exception:
            continue

def _load_plugin_package(plugin_path: Path):
    """Load a plugin package file that contains multiple nodes"""
    global _templates, _plugin_packages
    
    try:
        with plugin_path.open('r', encoding='utf-8') as f:
            package_data = json.load(f)
        
        # Check if it's a package (has 'nodes' array)
        if 'nodes' not in package_data:
            # Single node format - load normally
            name = package_data.get('name') or plugin_path.stem
            package_data.setdefault('type', 'plugin')
            package_data['__path'] = str(plugin_path)
            package_data = _normalize_io_format(package_data)
            _templates[name] = package_data
            return
        
        # Package format - load all nodes
        package_name = package_data.get('package_name', plugin_path.stem)
        package_desc = package_data.get('description', '')
        nodes_list = []
        
        for node_data in package_data.get('nodes', []):
            node_name = node_data.get('name')
            if not node_name:
                continue
            
            # Add package metadata
            node_data.setdefault('type', 'plugin')
            node_data['__path'] = str(plugin_path)
            node_data['__package'] = package_name
            node_data = _normalize_io_format(node_data)
            
            _templates[node_name] = node_data
            nodes_list.append(node_name)
        
        # Track package info
        _plugin_packages[package_name] = {
            'path': str(plugin_path),
            'description': package_desc,
            'nodes': nodes_list
        }
        
    except Exception as e:
        print(f"Error loading plugin package {plugin_path}: {e}")

def _load_plugin_archive(archive_path: Path):
    """Load a .ncpkg archive containing multiple node JSON files and Python modules"""
    global _templates, _plugin_packages, _plugin_modules
    
    try:
        package_name = archive_path.stem
        nodes_list = []
        package_desc = f'Plugin archive with nodes'
        
        with zipfile.ZipFile(archive_path, 'r') as zf:
            # Load package metadata if exists
            if 'package.json' in zf.namelist():
                with zf.open('package.json') as f:
                    pkg_meta = json.load(f)
                    package_desc = pkg_meta.get('description', package_desc)
            
            # Extract Python modules to cache directory
            module_files = [f for f in zf.namelist() if f.startswith('modules/') and f.endswith('.py')]
            if module_files:
                package_cache_dir = PLUGIN_CACHE_DIR / package_name
                package_cache_dir.mkdir(parents=True, exist_ok=True)
                
                for module_file in module_files:
                    module_path = package_cache_dir / Path(module_file).name
                    with zf.open(module_file) as src:
                        with open(module_path, 'wb') as dst:
                            dst.write(src.read())
                
                # Load the first Python module (or a specific one if named plugin.py)
                main_module = None
                for module_file in module_files:
                    if Path(module_file).name == 'plugin.py' or main_module is None:
                        main_module = module_file
                        if Path(module_file).name == 'plugin.py':
                            break
                
                if main_module:
                    import sys
                    import importlib.util
                    
                    module_path = package_cache_dir / Path(main_module).name
                    spec = importlib.util.spec_from_file_location(f"plugin_{package_name}", module_path)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[f"plugin_{package_name}"] = module
                        spec.loader.exec_module(module)
                        _plugin_modules[package_name] = module
            
            # Load node JSON files
            for file_info in zf.filelist:
                if file_info.filename.endswith('.json') and not file_info.filename == 'package.json':
                    with zf.open(file_info) as f:
                        node_data = json.load(f)
                        node_name = node_data.get('name', Path(file_info.filename).stem)
                        
                        node_data.setdefault('type', 'plugin')
                        node_data['__path'] = str(archive_path)
                        node_data['__package'] = package_name
                        node_data['__archive_file'] = file_info.filename
                        node_data = _normalize_io_format(node_data)
                        
                        _templates[node_name] = node_data
                        nodes_list.append(node_name)
        
        # Track package info
        _plugin_packages[package_name] = {
            'path': str(archive_path),
            'description': package_desc,
            'nodes': nodes_list,
            'has_module': package_name in _plugin_modules
        }
        
    except Exception as e:
        print(f"Error loading plugin archive {archive_path}: {e}")

def load_templates():
    """Load templates from `nodes/base`, `nodes/composite`, and `plugins` directories."""
    global _templates, _plugin_packages
    _templates = {}
    _plugin_packages = {}
    
    _load_from_dir(CORE_DIR, 'core')  # Load core system nodes first
    _load_from_dir(ANIMATION_DIR, 'animation')  # Load animation nodes
    _load_from_dir(BASE_DIR, 'base')
    _load_from_dir(PARTICLES_DIR, 'particles')
    _load_from_dir(COMPOSITE_DIR, 'composite')
    
    # Load plugins from plugins directory (both .json packages and .ncpkg archives)
    if PLUGINS_DIR.exists():
        for plugin_file in PLUGINS_DIR.iterdir():
            if plugin_file.suffix == '.json':
                _load_plugin_package(plugin_file)
            elif plugin_file.suffix == '.ncpkg':
                _load_plugin_archive(plugin_file)
    
    print(f"Loaded {len(_templates)} node templates (including plugins)")
    # If no base templates exist yet, create a few starter templates
    try:
        base_files = list(BASE_DIR.glob('*.json'))
        if not base_files:
            # create a simple Add, ConstInt and Return templates
            add = {
                'type': 'base',
                'name': 'Add',
                'category': 'Math',
                'inputs': {'a': 'float', 'b': 'float'},
                'outputs': {'result': 'float'},
                'code': 'name = "Add"\ninputs = {"a":"float","b":"float"}\noutputs = {"result":"float"}\ndef process(a, b):\n    return a + b\n'
            }
            const = {
                'type': 'base',
                'name': 'ConstInt',
                'category': 'Value',
                'inputs': {},
                'outputs': {'value': 'int'},
                'code': 'name = "ConstInt"\ninputs = {}\noutputs = {"value":"int"}\ndef process():\n    return 0\n'
            }
            ret = {
                'type': 'base',
                'name': 'Return',
                'category': 'Flow',
                'inputs': {'value': 'any'},
                'outputs': {},
                'code': 'name = "Return"\ninputs = {"value":"any"}\noutputs = {}\ndef process(value):\n    return None\n'
            }
            save_template(add)
            save_template(const)
            save_template(ret)
    except Exception:
        pass

def list_templates():
    return list(_templates.keys())

def get_template(name):
    return _templates.get(name)

def get_all_templates():
    """Return all loaded templates"""
    return _templates.copy()

def save_template(data: dict):
    # data should contain at least 'name' and 'type' (base|composite)
    name = data.get('name')
    if not name:
        raise ValueError('Template must have a name')
    ttype = data.get('type', 'base')
    if ttype == 'composite':
        p = COMPOSITE_DIR / f"{name}.json"
    else:
        p = BASE_DIR / f"{name}.json"
    with p.open('w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    data['type'] = ttype
    data['__path'] = str(p)
    _templates[name] = data

def delete_template(name: str):
    t = _templates.get(name)
    if not t:
        # try both locations
        for d in (BASE_DIR, COMPOSITE_DIR):
            p = d / f"{name}.json"
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass
        if name in _templates:
            del _templates[name]
        return
    p = Path(t.get('__path')) if t.get('__path') else None
    if p and p.exists():
        try:
            p.unlink()
        except Exception:
            pass
    if name in _templates:
        del _templates[name]

def save_graph(graph_data: dict, name: str):
    p = GRAPHS_DIR / f"{name}.json"
    with p.open('w', encoding='utf-8') as f:
        json.dump(graph_data, f, indent=2)

def get_plugin_packages():
    """Get list of plugin packages with their info"""
    return dict(_plugin_packages)

def get_package_nodes(package_name: str):
    """Get list of node names in a package"""
    if package_name in _plugin_packages:
        return _plugin_packages[package_name].get('nodes', [])
    return []

def get_plugin_module(package_name: str):
    """Get the Python module for a plugin package if it exists"""
    return _plugin_modules.get(package_name)

def get_node_module(node_name: str):
    """Get the Python module associated with a node's package"""
    template = _templates.get(node_name)
    if template and '__package' in template:
        return get_plugin_module(template['__package'])
    return None

# load on import
load_templates()
