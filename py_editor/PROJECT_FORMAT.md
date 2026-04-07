# Multi-Graph Project Format

Projects are stored as `.ncproject` (NodeCanvas Project) JSON files with this structure:

```json
{
  "version": "1.0",
  "name": "MyProject",
  "graphs": {
    "Main": {
      "nodes": [...],
      "connections": [...]
    },
    "Utility": {
      "nodes": [...],
      "connections": [...]
    }
  },
  "variables": {
    "globalVar1": 42,
    "globalVar2": "hello"
  },
  "metadata": {
    "created": "2025-12-06",
    "modified": "2025-12-06"
  }
}
```

## Features:
- Multiple named graphs in one project
- Shared global variables across graphs
- Call other graphs using CallGraph node
- Import/export entire projects
