# uproot Architecture

## Overview
uproot is a Python web framework for building browser-based behavioral experiments and multi-participant studies. Built on FastAPI/ASGI with real-time capabilities via WebSockets.

## Core Components

### Server Layer
- **FastAPI Application** (`server.py`): ASGI app with three router modules (server1/2/3) handling different endpoint groups
- **Real-time Communication**: WebSocket support for live participant interaction
- **Static Assets**: Bootstrap, Alpine.js, custom JS/CSS in `static/`

### Experiment Management
- **Sessions**: Isolated experiment instances with participants and configuration
- **Rooms**: Finite state machines controlling participant flow and capacity
- **Pages**: Template-driven experiment screens with Jinja2 rendering
- **Module System** (`modules.py`): Hot-reloadable experiment modules with file watching

### Data Layer
- **Storage System** (`storage.py`): Hierarchical append-only data model with caching
- **Database Integration**: Pluggable backends (default is Sqlite3, PostgreSQL optional)
- **Event System** (`events.py`): Participant attendance and room state tracking

### State Management
- **Global State** (`__init__.py`): In-memory tracking of online participants, session info, manual dropouts
- **Persistence**: Session data persisted across server restarts
- **Jobs** (`jobs.py`): Background tasks for synchronization and restoration

### Web Interface
- **Admin Panel**: Session management, monitoring, data visualization
- **Participant Interface**: Dynamic page routing based on experiment flow
- **Templates**: HTML templates in `default/` with admin-specific templates

## Key Patterns
- **Type Safety**: Extensive use of Pydantic for validation and type checking
- **Context Management**: Storage instances use context managers for data consistency
- **Plugin Architecture**: Modular experiment design via importable modules
- **Event-Driven**: Participant actions trigger state updates and notifications
