/**
 * Data viewer table for admin session data view.
 * Displays player field data with filtering and historical state tracking.
 *
 * Note: This file mixes camelCase and snake_case as much data comes from Python.
 */

// ============================================================================
// Constants
// ============================================================================

// Payload tuple indices (data format from Python backend)
const PAYLOAD = {
    TIME: 0,           // Timestamp of the change
    UNAVAILABLE: 1,    // Whether the field is unavailable/deleted
    TYPE: 2,           // Python type name
    VALUE: 3,          // The actual value (display representation)
    CONTEXT: 4         // Context where the change occurred
};

// Fields that should not be displayed in the table
const IGNORED_FIELDS = ["session", "key"];

// Fields that should appear first in the table (in order)
const PRIORITY_FIELDS = [
    "id", "label", "_uproot_group", "member_id",
    "page_order", "show_page", "started", "round"
];

// Table configuration
const VALUE_MAX_LENGTH = 30;
const HIGHLIGHT_DURATION_MS = 3000;

// ============================================================================
// Module State
// ============================================================================

const viewdataState = {
    filter: {},
    lastData: null,
    lastUpdate: 0,
    table: null,
    currentContainer: "tableOuter",
    fullDataset: {},
    recentlyUpdated: new Set(),
    rowHeight: 41
};

// ============================================================================
// Field Utilities
// ============================================================================

/**
 * Compares two fields for sorting, prioritizing fields in PRIORITY_FIELDS.
 */
function prioritizeFields(a, b) {
    const ai = PRIORITY_FIELDS.indexOf(a);
    const bi = PRIORITY_FIELDS.indexOf(b);

    if (ai !== -1 && bi !== -1) return ai - bi;
    if (ai !== -1) return -1;
    if (bi !== -1) return 1;
    return a.localeCompare(b);
}

/**
 * Transforms internal field names to display names.
 */
function transformField(field) {
    if (field === "_uproot_group") {
        return "(group)";
    }
    return field;
}

/**
 * Checks if a field should be included in the table.
 */
function shouldIncludeField(field) {
    if (IGNORED_FIELDS.includes(field)) return false;
    if (field.startsWith("_uproot_") && field !== "_uproot_group") return false;
    return true;
}

// ============================================================================
// Cell Formatting
// ============================================================================

/**
 * Formats a cell value for display, with truncation and metadata tooltip.
 */
function formatCellValue(value, metadata) {
    if (!metadata || metadata.unavailable) {
        return `<small class="text-secondary">(${_("unset")})</small>`;
    }

    const str = String(value);
    const displayValue = str.length > VALUE_MAX_LENGTH
        ? str.substring(0, VALUE_MAX_LENGTH - 3) + "..."
        : str;

    if (metadata && metadata.time) {
        const tooltip = `${epochToLocalISO(metadata.time)} @ ${metadata.context}`;
        return `<span class="a-value" title="${tooltip}" style="cursor: pointer;">${displayValue}</span>`;
    }

    return displayValue;
}

/**
 * Shows a modal with detailed cell information.
 */
function showCellDetails(field, metadata) {
    if (!metadata || metadata.no_details) return;

    const typeLabel = _("Type");
    const lastChangedLabel = _("Last changed");
    const unsetLabel = _("Unset or deleted");

    let details;
    if (!metadata || metadata.unavailable) {
        details = `<h4>${uproot.escape(field)}</h4>
            <p><strong>${unsetLabel}</strong></p>
            <p><strong>${lastChangedLabel}:</strong> ${epochToLocalISO(metadata.time)} @ ${uproot.escape(metadata.context)}</p>`;
    } else {
        details = `<h4>${uproot.escape(field)}</h4>
            <p><strong>${typeLabel}:</strong> ${uproot.escape(metadata.type) || `<i>${_("Unknown")}</i>`}</p>
            <p><strong>${lastChangedLabel}:</strong> ${epochToLocalISO(metadata.time)} @ ${uproot.escape(metadata.context)}</p>
            <textarea class="form-control" rows="8" disabled>${uproot.escape(metadata.trueValue) || ""}</textarea>`;
    }

    uproot.alert(details);
}

// ============================================================================
// Column Detection
// ============================================================================

/**
 * Detects the appropriate column type based on the Python type in the data.
 */
function detectColumnType(field, data) {
    for (const playerData of Object.values(data)) {
        const payload = playerData[field];
        if (payload && payload.length === 5) {
            const type = payload[PAYLOAD.TYPE].toLowerCase();

            if (type.includes("int") || type.includes("float") || type.includes("decimal")) {
                return "number";
            }
            if (type.includes("bool")) {
                return "boolean";
            }
        }
    }
    return "string";
}

// ============================================================================
// Column Creation
// ============================================================================

/**
 * Determines the widths (in pixels) of columns based on their field names.
 */
function getColumnWidth(field) {
    if (field === "id") return 75;
    if (field === "label") return 125;
    if (field === "page_order") return 330;
    if (field === "player") return 125;
    return 140;  // default
}

/**
 * Creates column definitions for the Tabulator table.
 */
function createColumns(data) {
    const columns = [{
        title: "player",
        field: "player",
        frozen: true,
        width: getColumnWidth("player"),
        headerFilter: "input"
    }];

    // Get all unique fields from data
    const allFields = new Set();
    Object.values(data).forEach(playerData => {
        Object.keys(playerData).forEach(field => {
            if (shouldIncludeField(field)) {
                allFields.add(transformField(field));
            }
        });
    });

    // Sort fields by priority
    const sortedFields = Array.from(allFields).sort(prioritizeFields);

    sortedFields.forEach((field, index) => {
        const detectedType = detectColumnType(field, data);

        columns.push({
            title: field,
            field: field,
            frozen: index < 2,
            width: getColumnWidth(field),
            headerFilter: "input",
            sorter: detectedType,
            formatter: createCellFormatter(field),
            cellClick: createCellClickHandler(field)
        });
    });

    return columns;
}

/**
 * Creates a formatter function for a specific field.
 */
function createCellFormatter(field) {
    return function(cell, formatterParams, onRendered) {
        const value = cell.getValue();
        const metadata = cell.getRow().getData()[field + "_meta"];
        const cellKey = `${cell.getRow().getData().player}:${field}`;
        const isUpdated = viewdataState.recentlyUpdated.has(cellKey);

        const formattedValue = formatCellValue(value, metadata);

        if (isUpdated) {
            onRendered(() => {
                const element = cell.getElement();
                element.classList.add("bg-success-subtle");
                setTimeout(() => {
                    element.classList.remove("bg-success-subtle");
                }, HIGHLIGHT_DURATION_MS);
            });
        }

        return formattedValue;
    };
}

/**
 * Creates a click handler for a specific field.
 */
function createCellClickHandler(field) {
    return function(e, cell) {
        const clickedField = cell.getColumn().getField();
        const metadata = cell.getRow().getData()[clickedField + "_meta"];
        if (clickedField !== "player") {
            showCellDetails(clickedField, metadata);
        }
    };
}

// ============================================================================
// Data Transformation
// ============================================================================

/**
 * Transforms raw data into the format expected by Tabulator.
 */
function transformDataForTabulator(rawData) {
    const transformedData = [];

    for (const [uname, allfields] of Object.entries(rawData)) {
        const row = { player: uname };

        for (const [originalField, payload] of Object.entries(allfields)) {
            if (!shouldIncludeField(originalField)) continue;

            const field = transformField(originalField);

            // Store the display value
            row[field] = payload[PAYLOAD.VALUE];

            // Store metadata for tooltips and modals
            row[field + "_meta"] = {
                path: [uname, field],
                time: payload[PAYLOAD.TIME],
                unavailable: payload[PAYLOAD.UNAVAILABLE],
                type: payload[PAYLOAD.TYPE],
                trueValue: payload[PAYLOAD.VALUE],
                context: payload[PAYLOAD.CONTEXT],
                no_details: originalField === "_uproot_group"
            };
        }

        transformedData.push(row);
    }

    return transformedData;
}

// ============================================================================
// Table Management
// ============================================================================

/**
 * Creates and initializes the Tabulator table.
 */
function createTable(containerId) {
    viewdataState.currentContainer = containerId;

    if (viewdataState.table) {
        viewdataState.table.destroy();
    }

    const container = containerId === "tableOuter"
        ? document.querySelector("#tableOuter")
        : document.getElementById(containerId);

    const tableEl = document.createElement("div");
    tableEl.id = "data-table";
    container.innerHTML = "";
    container.appendChild(tableEl);

    viewdataState.table = new Tabulator("#data-table", {
        columns: [{
            title: "player",
            field: "player",
            frozen: true,
            width: 120,
            headerFilter: "input"
        }],
        data: [],
        height: containerId === "tableModalInner" ? "100%" : "400px",
        layout: "fitColumns",
        placeholder: _("No data available"),
        rowHeight: viewdataState.rowHeight
    });
}

// ============================================================================
// Data Merging and State
// ============================================================================

/**
 * Merges differential data into the full dataset and tracks updated cells.
 */
function mergeDiffIntoDataset(diffData) {
    viewdataState.recentlyUpdated.clear();

    for (const [uname, fields] of Object.entries(diffData)) {
        if (!viewdataState.fullDataset[uname]) {
            viewdataState.fullDataset[uname] = { ...fields };
        } else {
            for (const [field, arr] of Object.entries(fields)) {
                const existing = viewdataState.fullDataset[uname][field];
                viewdataState.fullDataset[uname][field] = existing
                    ? [...existing, ...arr]
                    : [...arr];
            }
        }

        // Track changed fields
        for (const field of Object.keys(fields)) {
            viewdataState.recentlyUpdated.add(`${uname}:${transformField(field)}`);
        }
    }
}

/**
 * Computes the latest state of all fields, optionally filtered by conditions.
 * Uses "within-adjacent" temporal logic.
 */
function latest(obj, conditions = {}) {
    const result = {};

    for (const [uname, fields] of Object.entries(obj)) {
        // Collect all changes
        const changes = [];

        for (const [field, values] of Object.entries(fields)) {
            for (let i = 0; i < values.length; i++) {
                changes.push({
                    time: values[i][PAYLOAD.TIME],
                    field: field,
                    unavailable: values[i][PAYLOAD.UNAVAILABLE],
                    data: values[i][PAYLOAD.VALUE],
                    payload: values[i]
                });
            }
        }

        // Sort by time
        changes.sort((a, b) => a.time - b.time);

        // Build state evolution
        const currentState = {};
        let latestValidState = null;

        for (const change of changes) {
            currentState[change.field] = change.payload;

            // Check if all conditions are met
            let allConditionsMet = true;

            if (Object.keys(conditions).length > 0) {
                for (const [condField, condValue] of Object.entries(conditions)) {
                    const fieldState = currentState[condField];

                    if (!fieldState ||
                        fieldState[PAYLOAD.UNAVAILABLE] ||
                        fieldState[PAYLOAD.VALUE] !== condValue) {
                        allConditionsMet = false;
                        break;
                    }
                }
            }

            if (allConditionsMet) {
                latestValidState = { ...currentState };
            }
        }

        if (latestValidState) {
            // Apply temporal constraint
            const filteredState = {};

            for (const [field, payload] of Object.entries(latestValidState)) {
                let includeField = true;

                if (Object.keys(conditions).length > 0 && !Object.hasOwn(conditions, field)) {
                    const fieldTime = payload[PAYLOAD.TIME];

                    for (const condField of Object.keys(conditions)) {
                        if (latestValidState[condField]) {
                            const condTime = latestValidState[condField][PAYLOAD.TIME];
                            if (condTime > fieldTime) {
                                includeField = false;
                                break;
                            }
                        }
                    }
                }

                if (includeField) {
                    filteredState[field] = payload;
                }
            }

            result[uname] = filteredState;
        }
    }

    return result;
}

// ============================================================================
// App Filter Dropdown
// ============================================================================

/**
 * Populates the app filter dropdown with all unique app names.
 */
function writeAllAppNames() {
    const extractAppNames = (app) => {
        if (!Array.isArray(app)) return [];

        if (app.some(Array.isArray)) {
            return app
                .filter(Array.isArray)
                .map(arr => arr[PAYLOAD.VALUE])
                .filter(value => value !== undefined);
        }

        return app[PAYLOAD.VALUE] !== undefined ? [String(app[PAYLOAD.VALUE])] : [];
    };

    const allAppNames = [...new Set(
        Object.values(viewdataState.fullDataset)
            .flatMap(({ app }) => extractAppNames(app))
    )];

    const container = I("all-app-names");
    if (!container) return;

    container.innerHTML = "";

    // Add "Any app" option
    const defaultItem = document.createElement("li");
    const defaultSpan = document.createElement("span");
    defaultSpan.className = "dropdown-item fst-italic";
    defaultSpan.setAttribute("role", "button");
    defaultSpan.textContent = _("Any app");
    defaultSpan.onclick = () => {
        filterThenRefreshData("app", "");
        I("current-app-filter").textContent = "";
    };
    defaultItem.appendChild(defaultSpan);
    container.appendChild(defaultItem);

    // Add divider
    const divider = document.createElement("li");
    const hr = document.createElement("hr");
    hr.className = "dropdown-divider";
    divider.appendChild(hr);
    container.appendChild(divider);

    // Add app names
    allAppNames
        .filter(name => name !== "None")
        .forEach(name => {
            const li = document.createElement("li");
            const span = document.createElement("span");
            span.className = "dropdown-item font-monospace";
            span.setAttribute("role", "button");
            span.textContent = name;
            span.onclick = () => {
                filterThenRefreshData("app", name);
                I("current-app-filter").textContent = ` | ${name}`;
            };
            li.appendChild(span);
            container.appendChild(li);
        });
}

// ============================================================================
// Filtering
// ============================================================================

/**
 * Clears all filters and refreshes the data.
 */
function removeFilter() {
    viewdataState.filter = {};
    refreshData();

    const roundInput = I("filter-by-round-input");
    const appFilter = I("current-app-filter");

    if (roundInput) roundInput.value = "";
    if (appFilter) appFilter.textContent = "";
}

/**
 * Updates a filter key and refreshes the data.
 */
function filterThenRefreshData(key, value) {
    if (value === "" && Object.keys(viewdataState.filter).length > 0) {
        // Remove the key
        const { [key]: _, ...rest } = viewdataState.filter;
        viewdataState.filter = rest;
    } else {
        // Add or update
        viewdataState.filter = { ...viewdataState.filter, [key]: value };
    }
    refreshData();
}

// ============================================================================
// Data Updates
// ============================================================================

/**
 * Fetches new data from the server and updates the table.
 */
async function updateData() {
    try {
        const firstLoad = viewdataState.lastUpdate === 0;

        const [lastData, lastUpdate] = await uproot.invoke(
            "everything_from_session_display",
            uproot.vars.sname,
            viewdataState.lastUpdate
        );

        viewdataState.lastData = lastData;
        viewdataState.lastUpdate = lastUpdate;

        // Merge the diff into our full dataset
        mergeDiffIntoDataset(lastData);

        if (viewdataState.table) {
            const latestOnly = latest(viewdataState.fullDataset, viewdataState.filter);
            const transformedData = transformDataForTabulator(latestOnly);
            const columns = createColumns(latestOnly);

            // Update columns if they've changed
            const currentColumnFields = viewdataState.table.getColumnDefinitions().map(col => col.field);
            const newColumnFields = columns.map(col => col.field);

            if (JSON.stringify(currentColumnFields) !== JSON.stringify(newColumnFields)) {
                viewdataState.table.setColumns(columns);
            }

            viewdataState.table.setData(transformedData);

            if (firstLoad) {
                viewdataState.table.setSort("id", "asc");
            }
        }
    } catch (error) {
        console.error("Error updating data:", error);
        if (viewdataState.table) {
            viewdataState.table.setData([]);
        }
    }

    writeAllAppNames();
}

/**
 * Refreshes data while preserving scroll position.
 */
async function refreshData() {
    const tableHolder = document.getElementsByClassName("tabulator-tableholder")[0];
    if (!tableHolder) return;

    const scrollPosX = tableHolder.scrollLeft;
    const scrollPosY = tableHolder.scrollTop;

    await updateData();

    tableHolder.scrollLeft = scrollPosX;
    tableHolder.scrollTop = scrollPosY;
}

/**
 * Initializes the table and loads initial data.
 */
function initializeTable() {
    createTable(viewdataState.currentContainer);
    updateData();
}
