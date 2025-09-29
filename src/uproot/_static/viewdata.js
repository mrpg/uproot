// This file mixes camelCase and snake_case as much data comes from Python

const ignoredFields = ["session", "key"];
const priorityFields = ["id", "label", "_uproot_group", "member_id", "page_order", "show_page", "started", "round"];

let FILTER = {};  // TODO: grouping var, actually
let lastData, lastUpdate = 0;
let table;
let currentContainer = "tableOuter";
let fullDataset = {};
let recentlyUpdated = new Set();

function prioritizeFields(a, b) {
    const ai = priorityFields.indexOf(a);
    const bi = priorityFields.indexOf(b);

    if (ai !== -1 && bi !== -1) return ai - bi;  // both prioritized
    if (ai !== -1) return -1;                    // a is priority
    if (bi !== -1) return 1;                     // b is priority
    return a.localeCompare(b);                   // alphabetical for the rest
}

function transformField(field) {
    if (field === "_uproot_group") {
        return "(group)";
    }
    return field;
}

function formatCellValue(value, metadata) {
    if (!metadata || metadata.unavailable) {
        return "<small class='text-muted'>(" + _("unset") + ")</small>";
    }

    const str = String(value);
    const displayValue = str.length > 30 ? str.substr(0, 27) + "..." : str;
    // 27, since "...".length = 3

    // Add tooltip and click styling if metadata exists
    if (metadata && metadata.time) {
        const tooltip = `${epochToLocalISO(metadata.time)} @ ${metadata.context}`;
        return `<span class="a-value" title="${tooltip}" style="cursor: pointer;">${displayValue}</span>`;
    }

    return displayValue;
}

function showCellDetails(field, metadata) {
    if (!metadata || metadata.no_details) return;

    let details;
    const typeLabel = _("Type");
    const lastChangedLabel = _("Last changed");
    const unsetLabel = _("Unset or deleted");

    if (!metadata || metadata.unavailable) {
        details = `<h4>${uproot.escape(field)}</h4>
            <p><strong>${unsetLabel}</strong></p>
            <p><strong>${lastChangedLabel}:</strong> ${epochToLocalISO(metadata.time)} @ ${uproot.escape(metadata.context)}</p>`;
    }
    else {
        details = `<h4>${uproot.escape(field)}</h4>
            <p><strong>${typeLabel}:</strong> ${uproot.escape(metadata.type) || `<i>${_("Unknown")}</i>`}</p>
            <p><strong>${lastChangedLabel}:</strong> ${epochToLocalISO(metadata.time)} @ ${uproot.escape(metadata.context)}</p>
            <textarea class="form-control" rows="8" disabled>${uproot.escape(metadata.trueValue) || ''}</textarea>`;
    }

    uproot.alert(details); // SAFE
}

function detectColumnType(field, data) {
    for (const playerData of Object.values(data)) {
        if (playerData[field] && playerData[field].length == 5) {
            const type = playerData[field][2].toLowerCase();

            if (type.includes("int") || type.includes("float") || type.includes("decimal")) {
                return "number";
            }
            if (type.includes("bool")) {
                return "boolean";
            }
        }
    }

    return "string"; // default
}

function createColumns(data) {
    const columns = [{
        title: "player",
        field: "player",
        frozen: true,
        width: 110,
        headerFilter: "input"
    }];

    // Get all unique fields from data
    const allFields = new Set();
    Object.values(data).forEach(playerData => {
        Object.keys(playerData).forEach(field => {
            if (!field.startsWith("_uproot_") || field === "_uproot_group") {
                if (!ignoredFields.includes(field)) {
                    allFields.add(transformField(field));
                }
            }
        });
    });

    // Sort fields by priority
    const sortedFields = Array.from(allFields).sort(prioritizeFields);

    sortedFields.forEach((field, index) => {
        const detectedType = detectColumnType(field, data);
        const colWidth = field == "id" ? 110 : (field == "page_order" ? 330 : 150);
        columns.push({
            title: field,
            field: field,
            frozen: index < 2,
            width: colWidth,
            headerFilter: "input",
            sorter: detectedType, // Use detected type
            formatter: function (cell, formatterParams, onRendered) {
                const value = cell.getValue();
                const metadata = cell.getRow().getData()[field + "_meta"];
                const cellKey = `${cell.getRow().getData().player}:${field}`;
                const isUpdated = recentlyUpdated.has(cellKey);

                const formattedValue = formatCellValue(value, metadata);

                if (isUpdated) {
                    // Add table-active class to the cell element
                    onRendered(function () {
                        //cell.getElement().classList.add('bg-opacity-75');
                        cell.getElement().classList.add('bg-success-subtle');
                        window.setTimeout(function () {
                            cell.getElement().classList.remove('bg-success-subtle');
                        }, 3000);
                    });
                }

                return formattedValue;
            },
            cellClick: function (e, cell) {
                const field = cell.getColumn().getField();
                const metadata = cell.getRow().getData()[field + "_meta"];
                if (field !== "player") {
                    showCellDetails(field, metadata);
                }
            }
        });
    });

    return columns;
}

function transformDataForTabulator(rawData) {
    const transformedData = [];

    for (const [uname, allfields] of Object.entries(rawData)) {
        const row = { player: uname };

        for (const [originalField, payload] of Object.entries(allfields)) {
            const field = transformField(originalField);

            if (!originalField.startsWith("_uproot_") || originalField === "_uproot_group") {
                if (!ignoredFields.includes(originalField)) {
                    // Store the display value
                    row[field] = payload[3];

                    // Store metadata for tooltips and modals
                    row[field + "_meta"] = {
                        path: [uname, field],
                        time: payload[0],
                        unavailable: payload[1],
                        type: payload[2],
                        trueValue: payload[3],
                        context: payload[4],
                        no_details: originalField === "_uproot_group" // Set no_details for group fields
                    };
                }
            }
        }

        transformedData.push(row);
    }

    return transformedData;
}

function createTable(containerId) {
    currentContainer = containerId;

    if (table) {
        table.destroy();
    }

    const container = containerId === "tableOuter" ?
        document.querySelector("#tableOuter") :
        document.getElementById(containerId);

    // Create table element
    const tableEl = document.createElement("div");
    tableEl.id = "data-table";
    container.innerHTML = "";
    container.appendChild(tableEl);

    table = new Tabulator("#data-table", {
        height: containerId === "tableModalInner" ? "100%" : "400px",
        layout: "fitColumns",
        placeholder: _("No data available"),
        columns: [{ // Start with just player column
            title: "player",
            field: "player",
            frozen: true,
            width: 120,
            headerFilter: "input"
        }],
        data: [],
    });
}

function mergeDiffIntoDataset(diffData) {
    // Clear previous updates and track new ones
    recentlyUpdated.clear();

    // Merge the diff data into our full dataset
    for (const [uname, fields] of Object.entries(diffData)) {
        if (!fullDataset[uname]) {
            fullDataset[uname] = { ...fields };
        }
        else {
            for (const [field, arr] of Object.entries(fields)) {
                fullDataset[uname][field] = fullDataset[uname][field] ? [...fullDataset[uname][field], ...arr] : [...arr];
            }
        }

        // Update only the changed fields for this user
        for (const [field, payload] of Object.entries(fields)) {
            // Track this cell as recently updated
            recentlyUpdated.add(`${uname}:${transformField(field)}`);
        }
    }
}

function latest(obj, conditions = {}) {
    const result = {};

    for (const [uname, fields] of Object.entries(obj)) {
        // Collect all changes
        const changes = [];

        for (const [field, values] of Object.entries(fields)) {
            for (let i = 0; i < values.length; i++) {
                changes.push({
                    time: values[i][0],
                    field: field,
                    unavailable: values[i][1],
                    data: values[i][3],
                    payload: values[i]
                });
            }
        }

        // Sort by time (just to be safe)
        changes.sort((a, b) => a.time - b.time);

        // Build state evolution
        const currentState = {};
        let latestValidState = null;

        for (const change of changes) {
            // Update current state
            currentState[change.field] = change.payload;

            // Check if all conditions are met
            let allConditionsMet = true;

            if (Object.keys(conditions).length > 0) {
                for (const [condField, condValue] of Object.entries(conditions)) {
                    const fieldState = currentState[condField];

                    if (!fieldState || fieldState[1] || fieldState[3] !== condValue) {
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
            result[uname] = latestValidState;
        }
    }

    return result;
}

function writeAllAppNames() {
    // TODO: Work on this for full release
    /* fullDataset is a dictionary in JavaScript with player names as the keys. For each key, the value is a dictionary that has a key callded “app.” That key is either an array with 5 entries or a nested array of multiple inner arrays. All inner arrays have 5 entries. We generate a list of all unique values of the 4th entry of all innermost arrays. */
    const allAppNames = [...new Set(
        Object.values(fullDataset).flatMap(({ app }) => {
            if (!Array.isArray(app)) return [];
            // If it's an array of arrays, take index 3 from each inner array
            if (app.some(Array.isArray)) {
            return app
                .filter(Array.isArray)
                .map(a => a[3])
                .filter(v => v !== undefined);
            }
            // Otherwise it's a single 5-item array
            return app[3] !== undefined ? [String(app[3])] : [];
        })
    )];
    I("all-app-names").innerHTML =
        `<li><span class="dropdown-item fst-italic" onclick="filterThenRefreshData('app', ''); I('current-app-filter').textContent = ''" role="button">${_("Any app")}</li>` +
        `<li><hr class="dropdown-divider"></li>`;
    for (let i = 0; i < allAppNames.length; i++) {
        const name = allAppNames[i];
        I("all-app-names").innerHTML +=
            name == "None" ? `` :
            `<li><span class="dropdown-item font-monospace" onclick="filterThenRefreshData('app', '${name}'); I('current-app-filter').textContent = ' | ${name}'" role="button">${name}</li>`;
    }
}

function removeFilter() {
    FILTER = {};
    refreshData();
    I("round-filter").value = "";
    I('current-app-filter').textContent = "";
}

function filterThenRefreshData(key, value) {
    if (value == "" & FILTER != {}) {  // Remove the key
        const { [key]: _, ...rest } = FILTER;
        FILTER = rest;
    } else {  // Add or update
        FILTER = { ...FILTER, [key]: value };
    }
    refreshData();
    console.log(FILTER);
}

async function updateData() {
    try {
        const firstLoad = lastUpdate == 0;

        [lastData, lastUpdate] = await uproot.invoke("everything_from_session_display", uproot.vars.sname, lastUpdate);

        // Merge the diff into our full dataset
        mergeDiffIntoDataset(lastData);

        if (table) {
            const latestOnly = latest(fullDataset, FILTER);
            const transformedData = transformDataForTabulator(latestOnly);
            const columns = createColumns(latestOnly);

            // Update columns if they've changed (only on significant changes)
            const currentColumnFields = table.getColumnDefinitions().map(col => col.field);
            const newColumnFields = columns.map(col => col.field);

            if (JSON.stringify(currentColumnFields) !== JSON.stringify(newColumnFields)) {
                table.setColumns(columns);
            }

            // Update data with full merged dataset
            table.setData(transformedData);

            if (firstLoad) {
                table.setSort("id", "asc");
            }
        }
    } catch (error) {
        console.error("Error updating data:", error);
        if (table) {
            table.setData([]);
        }
    }

    writeAllAppNames();
}

async function refreshData() {
    const tableHolder = document.getElementsByClassName("tabulator-tableholder")[0];
    if (!tableHolder) return;
    const scrollPosX = tableHolder.scrollLeft;
    const scrollPosY = tableHolder.scrollTop;
    await updateData();
    tableHolder.scrollLeft = scrollPosX;
    tableHolder.scrollTop = scrollPosY;
}

function initializeTable() {
    createTable(currentContainer);
    updateData();
}
