# uproot Framework Features

## Session & Experiment Management
- **Session Creation & Control**: Create isolated experiment sessions with unique identifiers
- **Room Management**: Finite state machine-controlled participant flow with optional capacity limits
- **Hot Module Reloading**: File watching system for live experiment development
- **Page Flow Control**: Define custom page sequences and navigation logic
- **Session Persistence**: Automatic session restoration after server restarts
- **Multi-Session Support**: Run multiple concurrent experiments

## Admin Interface & Monitoring
- **Web-Based Admin Panel**: Complete experiment management interface
- **Real-Time Participant Monitoring**: Live view of participant progress and status
- **Session Dashboard**: Overview of active sessions, rooms, and configurations
- **Manual Participant Control**: 
  - Advance/revert participants by one page
  - Force reload participant pages
  - Move participants to experiment end
  - Mark participants as dropouts
- **Field Insertion**: Emergency manual data field insertion during live experiments
- **Admin Messaging**: Send messages directly to participants during experiments

## Data Collection & Export
- **Real-Time Data Explorer**: Live data inspection during experiments
- **Append-Only Log**: Complete audit trail of all data changes
- **Hierarchical Data Model**: Admin/Session/Player/Group/Model data structure
- **Automatic Data Persistence**: All interactions and responses automatically stored
- **Multiple Export Formats**: CSV and JSON export with different layouts
- **Data Export Options**:
  - Ultra-long format (raw event data)
  - Sparse format (wide data structure)
  - Latest format (most recent values only)
- **Stealth Fields**: Store sensitive data elsewhere

## Form Fields & Input Components
- **Rich Form Field Library**:
  - StringField, TextAreaField for text input
  - IntegerField, DecimalField for numeric input
  - BooleanField for checkboxes
  - DateField for date selection
  - EmailField with validation
  - FileField for file uploads
  - RadioField, SelectField for multiple choice
  - LikertField for Likert scales (configurable range)
  - IBANField for banking information (requires optional dependency)
- **Field Validation**: Built-in validation with optional/required settings
- **Custom Field Layouts**: Horizontal/vertical radio button layouts
- **Slider without Anchoring**: Slider that does not implicitly suggest value

## Real-Time Communication
- **WebSocket Support**: Bidirectional real-time communication
- **On-Page Invocations**: Can safely invoke server functions from client
- **Full Async Support**
- **Robust WebSocket Client**: Auto-reconnecting WebSocket with message queuing
- **Chat System**: Built-in multi-participant chat functionality
- **Event Broadcasting**: Real-time event distribution to participants
- **Admin-Participant Messaging**: Direct communication channel
- **Connection Monitoring**: Track participant online/offline status

## Participant Management
- **Unique Player Identification**: Session-scoped participant identifiers
- **Online Status Tracking**: Real-time participant presence monitoring
- **Dropout Handling**: Configurable dropout detection and handling
- **Group Management**: Organize participants into groups for multi-player experiments
- **Label System**: Pre-assigned participant labels for controlled entry
- **Capacity Controls**: Set maximum participants per room

## Multi-Language Support
- **Internationalization (i18n)**: Built-in translation system
- **Template Translation**: Automatic translation of template strings
- **CSV-Based Translations**: Manage translations via CSV files
- **Dynamic Language Loading**: Runtime language switching capability

## Templates & UI
- **Jinja2 Template Engine**: Flexible HTML template system
- **Bootstrap Integration**: Modern, responsive UI components
- **Custom CSS Framework**: uproot-branded styling system
- **Template Inheritance**: Base templates for consistent layouts
- **Alpine.js Integration**: Lightweight JavaScript framework for interactivity
- **Font Integration**: Inter font family with OpenType features
- **Responsive Design**: Mobile-friendly interface components

## API & Integration
- **FastAPI Backend**: Modern async Python web framework
- **Database Flexibility**: File-based storage with optional PostgreSQL support
- **CORS Support**: Cross-origin resource sharing for web integration

## Development & Deployment
- **Error Handling**: Comprehensive error pages
- **Error Reporting**: Client-side JavaScript errors reported to server
- **CLI Interface**: Command-line tools for project setup and management
- **Project Scaffolding**: Generate new experiment projects with templates
- **Example Applications**: Ready-to-use example experiments
- **Server with Reloading**: Built-in server performs hot reloading
- **Static File Serving**: Efficient per-app static asset delivery
- **Testing Framework**: Built-in testing utilities and fixtures

## Advanced Features
- **Query System**: Flexible data querying with field references and comparisons  
- **Storage Context Managers**: Safe data access patterns
- **Event System**: Extensible event handling for custom logic
- **Background Jobs**: Asynchronous task processing
- **Caching System**: Intelligent data caching with LRU eviction
- **Type Safety**: Full Pydantic integration for data validation
- **Flexible Function Decorators**: Automatic type conversion and validation
