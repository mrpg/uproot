// This file mixes camelCase and snake_case as much data comes from Python

const ignoredFields = ["session", "key"];
const priorityFields = ["id", "label", "_uproot_group", "member_id", "page_order", "show_page", "started", "round"];

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

function transformValue(field, payload) {
    if (field === "_uproot_group" && payload.value_representation) {
        const match = payload.value_representation.match(/gname='([^']+)'/);
        return match ? match[1] : payload.value_representation;
    }
    return payload.value_representation;
}

function formatCellValue(value, metadata) {
    if (value === null || value === undefined) {
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

    const typeLabel = typeof _ === 'function' ? _("Type") : "Type";
    const lastChangedLabel = typeof _ === 'function' ? _("Last changed") : "Last changed";

    const details = `
        <h4>${field}</h4>
        <p><strong>${typeLabel}:</strong> ${metadata.type || 'Unknown'}</p>
        <p><strong>${lastChangedLabel}:</strong> ${epochToLocalISO(metadata.time)} @ ${metadata.context}</p>
        <textarea class="form-control" rows="8" disabled>${metadata.trueValue || ''}</textarea>
    `;

    uproot.alert(details);
}

function detectColumnType(field, data) {
    for (const playerData of Object.values(data)) {
        if (playerData[field] && playerData[field].type_representation) {
            const type = playerData[field].type_representation.toLowerCase();
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
                    const value = transformValue(originalField, payload);

                    // Store the display value
                    row[field] = value;

                    // Store metadata for tooltips and modals
                    row[field + "_meta"] = {
                        time: payload.time,
                        context: payload.context,
                        type: payload.type_representation,
                        trueValue: value,
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
            fullDataset[uname] = {};
        }

        // Update only the changed fields for this user
        for (const [field, payload] of Object.entries(fields)) {
            fullDataset[uname][field] = payload;
            // Track this cell as recently updated
            recentlyUpdated.add(`${uname}:${transformField(field)}`);
        }
    }
}

async function updateData() {
    try {
        const firstLoad = lastUpdate == 0;

        [lastData, lastUpdate] = await uproot.invoke("viewdata", uproot.vars.sname, lastUpdate);

        if (lastData && Object.keys(lastData).length > 0) {
            // Merge the diff into our full dataset
            mergeDiffIntoDataset(lastData);

            if (table) {
                const transformedData = transformDataForTabulator(fullDataset);
                const columns = createColumns(fullDataset);

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
        }
    } catch (error) {
        console.error("Error updating data:", error);
        if (table) {
            table.setData([]);
        }
    }
}

function refreshData() {
    updateData();
}

function initializeTable() {
    // Reset dataset and lastUpdate for fresh start
    fullDataset = {};
    lastUpdate = 0;

    createTable(currentContainer);
    refreshData();
}
