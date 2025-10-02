const extraFields = ["started", "label", "round", "_uproot_group", "member_id"];
const heartbeats = {};

uproot.onStart(() => {
    createTable("tableOuter");
});

uproot.onStart(() => {
    loadExtraData();
    uproot.invoke("subscribe_to_attendance", uproot.vars.sname);
    uproot.invoke("subscribe_to_fieldchange", uproot.vars.sname, extraFields);
});

uproot.onCustomEvent("FieldChanged", (event) => {
    const data = {};
    const [pid, field, value] = event.detail;

    data[pid[2]] = {};
    data[pid[2]][field] = value.data;

    reshapeAndUpdateExtraData(data);
});

function loadExtraData() {
    uproot.invoke("fields_from_all", uproot.vars.sname, extraFields).then(reshapeAndUpdateExtraData);
}

function reshapeAndUpdateExtraData(data) {
    const newData = {};
    let startedCount = 0;

    for (const [key, value] of Object.entries(data)) {
        if (value._uproot_group !== undefined) {
            value.group = (value._uproot_group !== null) ? value._uproot_group.gname : null;
            delete value._uproot_group;
        }

        if (value.started !== undefined) {
            startedCount += value.started;
            delete value.started;
        }

        newData[key] = value;
    }

    I("started-count").textContent = startedCount; // TODO: Buggy
    updateExtraData(newData);
}

// Override createTable for monitor-specific setup
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

    // Get initial data to discover columns dynamically
    const initialData = getMonitorDataForTabulator();

    const columns = createMonitorColumns(initialData);

    table = new Tabulator("#data-table", {
        columns: columns,
        data: transformMonitorDataForTabulator(initialData),
        height: "100%",
        layout: "fitColumns",
        placeholder: "No players available",
        rowHeight: 44,  // must be provided in pixels
    });

    table.on("cellClick", (e, cell) => {
        if (e.target.tagName === "A") {
            return false;
        } else {
            cell.getRow().toggleSelect();
        }
    });

    // Wait for table to be built before setting up event handlers
    table.on("tableBuilt", function () {
        // Sort by ID initially
        if (initialData && Object.keys(initialData).length > 0) {
            table.setSort("id", "asc");
        }
    });

    return table;
}

function createMonitorColumns(data) {
    const columns = [
        {
            formatter: "rowSelection",
            titleFormatter: "rowSelection",
            hozAlign: "center",
            headerSort: false,
            width: 40,
        }
    ];

    // Get all unique fields from data
    const allFields = new Set();
    Object.values(data).forEach(playerData => {
        Object.keys(playerData).forEach(field => {
            if (!["pageOrder", "heartbeat"].includes(field)) {
                allFields.add(field);
            }
        });
    });

    // Sort fields by monitor priority
    const monitorPriorityFields = ["id", "label", "player", "page", "progress", "lastSeen", "round", "group", "member_id"];
    const sortedFields = Array.from(allFields).sort((a, b) => {
        const ai = monitorPriorityFields.indexOf(a);
        const bi = monitorPriorityFields.indexOf(b);

        if (ai !== -1 && bi !== -1) return ai - bi;  // both prioritized
        if (ai !== -1) return -1;                    // a is priority
        if (bi !== -1) return 1;                     // b is priority
        return a.localeCompare(b);                   // alphabetical for the rest
    });

    sortedFields.forEach((field, index) => {
        const frozen = ["id", "label", "player"].includes(field);

        const column = {
            title: field,
            field: field,
            frozen: frozen,
            headerFilter: "input"
        };

        // Add special formatters for specific fields
        if (field === "player") {
            column.formatter = function (cell) {
                const value = cell.getValue();
                const data = cell.getRow().getData();
                const heartbeat = data.heartbeat ? 'active' : '';
                return `<div class="d-flex align-items-center gap-2">
                    <a class="link-subtle player-name" href="${uproot.vars.root}/p/${uproot.vars.sname}/${value}/" target="_blank">${value}</a>
                    <span class="heartbeat ${heartbeat}" aria-hidden="true">♥</span>
                </div>`;
            };
        } else if (field === "page") {
            column.formatter = function (cell) {
                const path = cell.getValue() || "";
                const s = path.lastIndexOf("/");
                let dir = "", nameExt = path;
                if (s !== -1) { dir = path.slice(0, s + 1); nameExt = path.slice(s + 1); }

                const d = nameExt.lastIndexOf(".");
                let name = nameExt, ext = "";
                if (d > 0) { name = nameExt.slice(0, d); ext = nameExt.slice(d); }

                let html = "";
                if (dir) html += `<span class="app">${dir}</span>`;
                html += `<span class="page">${name}</span>`;
                if (ext) html += `<span class="extension">${ext}</span>`;
                return html;
            };
        } else if (field === "progress") {
            column.formatter = function (cell) {
                const data = cell.getRow().getData();
                const tooltip = Array.isArray(data.pageOrder) && data.pageOrder.length > 0 ? data.pageOrder.join(" → ") : "";
                return `<span title="${tooltip}">${cell.getValue()}</span>`;
            };
        } else if (field === "lastSeen") {
            column.formatter = function (cell) {
                const value = cell.getValue();
                if (!value || value === "—") return value;
                if (value.length >= 8) {
                    const hhmm = value.slice(-8, -3);
                    const ss = value.slice(-3);
                    return `<span title="${value}">${hhmm}<span class='text-secondary opacity-50'>${ss}</span></span>`;
                }
                return value;
            };
        }

        columns.push(column);
    });

    return columns;
}

function getMonitorDataForTabulator() {
    const info = uproot.vars.info || {};
    const online = uproot.vars.online || {};
    const extraData = uproot.vars.extraData || {};

    const monitorData = {};

    // Get all unique players from both info and extraData
    const allPlayers = new Set([...Object.keys(info), ...Object.keys(extraData)]);

    for (const uname of allPlayers) {
        const tuple = info[uname];
        const id = tuple?.[0];
        const pageOrder = Array.isArray(tuple?.[1]) ? tuple[1] : [];
        const showPage = Number.isInteger(tuple?.[2]) ? tuple[2] : -1;
        const pageName = ppath(pageOrder, showPage);
        const lastSeen = online?.[uname] == null ? "—" : epochToLocalISO(online[uname]);

        // Get heartbeat state
        const isHeartbeatActive = heartbeats[uname] === true;

        monitorData[uname] = {
            id: { value_representation: id ?? "", time: 0, context: "system" },
            player: { value_representation: uname, time: 0, context: "system" },
            page: { value_representation: pageName, time: 0, context: "system" },
            progress: { value_representation: `${Math.max(0, showPage + 1)}/${Math.max(0, pageOrder.length)}`, time: 0, context: "system" },
            lastSeen: { value_representation: lastSeen, time: 0, context: "system" },
            // Special fields that don't need metadata
            pageOrder: pageOrder,
            heartbeat: isHeartbeatActive
        };

        // Add extra data fields for this player
        if (extraData[uname]) {
            Object.keys(extraData[uname]).forEach(field => {
                monitorData[uname][field] = {
                    value_representation: extraData[uname][field],
                    time: Date.now() / 1000,
                    context: "extra"
                };
            });
        }
    }

    return monitorData;
}

function transformMonitorDataForTabulator(rawData) {
    const transformedData = [];

    for (const [uname, allfields] of Object.entries(rawData)) {
        const row = { player: uname };

        for (const [field, payload] of Object.entries(allfields)) {
            if (["pageOrder", "heartbeat"].includes(field)) {
                // Special fields without metadata
                row[field] = payload;
            } else {
                // Regular fields with value_representation
                row[field] = payload.value_representation;
            }
        }

        transformedData.push(row);
    }

    return transformedData;
}

async function updateData() {
    try {
        if (!table) return;

        const tableHolder = document.getElementsByClassName("tabulator-tableholder")[0];
        if (!tableHolder) return;
        const scrollPosX = tableHolder.scrollLeft;
        const scrollPosY = tableHolder.scrollTop;

        const rawData = getMonitorDataForTabulator();
        const transformedData = transformMonitorDataForTabulator(rawData);
        const columns = createMonitorColumns(rawData);

        // Wait for table to be built before updating
        if (table.initialized) {
            const currentColumnFields = table.getColumnDefinitions().map(col => col.field);
            const newColumnFields = columns.map(col => col.field);

            if (JSON.stringify(currentColumnFields) !== JSON.stringify(newColumnFields)) {
                // Save current sort and selected rows before recreating table
                const currentSort = table.getSorters();
                const selectedPlayers = getSelectedPlayers();
                createTable(currentContainer);
                // Restore sort and selection after table is built
                if (currentSort.length > 0 || selectedPlayers.length > 0) {
                    table.on("tableBuilt", function () {
                        if (currentSort.length > 0) {
                            table.setSort(currentSort);
                        }
                        if (selectedPlayers.length > 0) {
                            // Restore selected rows
                            selectedPlayers.forEach(player => {
                                const rows = table.searchRows("player", "=", player);
                                if (rows.length > 0) {
                                    rows[0].select();
                                }
                            });
                        }
                    });
                }
            } else {
                // Preserve current sort and selected rows when updating data
                const currentSort = table.getSorters();
                const selectedPlayers = getSelectedPlayers();
                table.setData(transformedData);
                // Restore sort if it was cleared
                if (currentSort.length > 0) {
                    table.setSort(currentSort);
                }
                // Restore selected rows
                if (selectedPlayers.length > 0) {
                    selectedPlayers.forEach(player => {
                        const rows = table.searchRows("player", "=", player);
                        if (rows.length > 0) {
                            rows[0].select();
                        }
                    });
                }
            }
            tableHolder.scrollLeft = scrollPosX;
            tableHolder.scrollTop = scrollPosY;
        } else {
            table.on("tableBuilt", function () {
                table.setData(transformedData);
            });
        }
    } catch (error) {
        console.error("Error updating monitor data:", error);
        if (table && table.initialized) {
            table.setData([]);
        }
    }
}

function ppath(pageOrder, showPage) {
    if (Array.isArray(pageOrder)) {
        if (Number.isInteger(showPage) && showPage >= 0 && showPage < pageOrder.length) {
            return pageOrder[showPage];
        }
        if (showPage === -1) return "Initialize.html";
    }
    return "End.html";
}

// Monitor-specific functions
window.newInfoOnline = function newInfoOnline(data) {
    if (!uproot) return;
    uproot.vars.online = data.online || {};
    uproot.vars.info = data.info || {};
    updateData();
};

window.updateExtraData = function updateExtraData(extraDataObj) {
    if (!uproot) return;
    if (!uproot.vars.extraData) uproot.vars.extraData = {};

    for (const [player, fields] of Object.entries(extraDataObj)) {
        if (!uproot.vars.extraData[player]) {
            uproot.vars.extraData[player] = {};
        }
        Object.assign(uproot.vars.extraData[player], fields);
    }

    updateData();
};

function getSelectedPlayers(col = "player") {
    if (!table || !table.initialized) return [];
    return table.getSelectedRows().map(row => row.getData()[col]);
}

function openMultiview() {
    const ids = getSelectedPlayers("id").sort().map(i => i.toString()).join(",");
    const max_iframes = 30;
    if (getSelectedPlayers("id").length < 1) {
        alert(_("No player selected. Select at least one player to be displayed in multiview."))
    } else if (getSelectedPlayers("id").length < max_iframes) {
        window.open(`./multiview/#${ids}`, "_blank");
    } else {
        alert(_(`Too many players (${getSelectedPlayers("id").length}) selected. The maximum number of players that can be displayed in multiview is ${max_iframes}.`))
    }
}

window.invokeFromMonitor = function invokeFromMonitor(fname, ...args) {
    return uproot.invoke(
        fname,
        uproot.vars.sname,
        getSelectedPlayers(),
        ...args,
    );
};

window.actuallyManage = function actuallyManage() {
    const action = uproot.selectedValue("manage");
    if (action) {
        window.bootstrap?.Modal.getOrCreateInstance(I("manage-modal")).hide();
        window.invokeFromMonitor(action).then((data) => {
            if (data) window.newInfoOnline(data);
            loadExtraData();
            uproot.alert("The action has completed.");
        });
    } else {
        uproot.error("No action selected.");
    }
};

window.actuallyInsert = function actuallyInsert() {
    const json = I("json-input")?.value ?? "";
    const reload = !!I("reload2")?.checked;
    let fields;
    try {
        fields = JSON.parse(json);
    } catch {
        return uproot.error("Invalid JSON.");
    }
    window.bootstrap?.Modal.getOrCreateInstance(I("insert-modal")).hide();
    window.invokeFromMonitor("insert_fields", { fields, reload }).then(() => {
        loadExtraData();
        uproot.alert("The action has completed.");
    });
};

window.actuallyAdminmessageSend = function actuallyAdminmessageSend() {
    const msg = I("adminmsg")?.value ?? "";
    window.bootstrap?.Modal.getOrCreateInstance(I("adminmessage_send-modal")).hide();
    window.invokeFromMonitor("adminmessage", msg).then(() => {
        uproot.alert("The action has completed.");
    });
};

window.mmodal = function mmodal(moname) {
    const selected = getSelectedPlayers();
    const modal = window.bootstrap?.Modal.getOrCreateInstance(I(`${moname}-modal`));
    if (selected.length > 0) {
        document.querySelectorAll(".pcount").forEach((el) => { el.innerText = String(selected.length); });
        modal?.show();
    } else {
        uproot.error("No players selected.");
    }
};

function triggerHeartbeat(uname) {
    if (!uproot) return;

    // Set heartbeat active
    heartbeats[uname] = true;

    // Update table to show heartbeat
    updateData();

    // Remove heartbeat after 5 seconds
    setTimeout(() => {
        if (heartbeats) {
            heartbeats[uname] = false;
            updateData(); // Update table to remove heartbeat
        }
    }, 5000);
}

uproot.onCustomEvent("Attended", (event) => {
    const uname = event?.detail?.uname;
    const info = event?.detail?.info;
    if (!uname || !Array.isArray(info)) return;

    // Update the uproot vars with new info
    if (!uproot.vars.info) uproot.vars.info = {};
    if (!uproot.vars.online) uproot.vars.online = {};

    // Update player info
    uproot.vars.info[uname] = info;
    uproot.vars.online[uname] = Date.now() / 1000; // Current timestamp in seconds

    // Trigger table refresh and heartbeat
    updateData();
    setTimeout(() => triggerHeartbeat(uname), 100); // Small delay to ensure table is updated
});
