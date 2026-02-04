/**
 * Player monitor table for admin session view.
 * Displays real-time player status, progress, and allows bulk player management.
 */

// ============================================================================
// Constants
// ============================================================================

const EXTRA_FIELDS = ["started", "label", "round", "_uproot_group", "member_id"];
const MONITOR_PRIORITY_FIELDS = ["id", "label", "player", "page", "progress", "lastSeen", "round", "group", "member_id"];
const MAX_MULTIVIEW_PLAYERS = 36;
const HEARTBEAT_DURATION_MS = 5000;
const UPDATE_DEBOUNCE_MS = 150;

// ============================================================================
// Module State
// ============================================================================

const monitorState = {
    table: null,
    currentContainer: "tableOuter",
    pendingUpdate: null,       // For debouncing
    activeHeartbeats: new Map(), // uname -> timeoutId (for cleanup)
    rowHeight: 44
};

// ============================================================================
// Initialization
// ============================================================================

uproot.onStart(() => {
    createTable("tableOuter");
    loadExtraData();
    uproot.invoke("subscribe_to_attendance", uproot.vars.sname);
    uproot.invoke("subscribe_to_fieldchange", uproot.vars.sname, EXTRA_FIELDS);

    // Initialize Alpine store counts once Alpine is ready
    document.addEventListener("alpine:initialized", () => {
        updateSessionStore();
    });
});

// ============================================================================
// Data Loading
// ============================================================================

function loadExtraData() {
    uproot.invoke("fields_from_all", uproot.vars.sname, EXTRA_FIELDS)
        .then(reshapeAndUpdateExtraData);
}

/**
 * Updates the Alpine store with current player counts.
 * Calculates total and started counts in a single pass.
 */
function updateSessionStore() {
    if (!window.Alpine || !Alpine.store("session")) return;

    const info = uproot.vars.info || {};
    let total = 0;
    let started = 0;

    for (const tuple of Object.values(info)) {
        total++;
        const showPage = Number.isInteger(tuple?.[2]) ? tuple[2] : -1;
        if (showPage >= 0) started++;
    }

    const store = Alpine.store("session");
    store.totalPlayers = total;
    store.startedCount = started;
}

function reshapeAndUpdateExtraData(data) {
    const newData = {};

    for (const [key, value] of Object.entries(data)) {
        if (value._uproot_group !== undefined) {
            value.group = (value._uproot_group !== null) ? value._uproot_group.gname : null;
            delete value._uproot_group;
        }

        // Remove started field if present (we derive it from showPage instead)
        if (value.started !== undefined) {
            delete value.started;
        }

        newData[key] = value;
    }

    updateExtraData(newData);
}

// ============================================================================
// Table Creation
// ============================================================================

function createTable(containerId) {
    monitorState.currentContainer = containerId;

    if (monitorState.table) {
        monitorState.table.destroy();
    }

    const container = containerId === "tableOuter"
        ? document.querySelector("#tableOuter")
        : document.getElementById(containerId);

    const tableEl = document.createElement("div");
    tableEl.id = "data-table";
    container.innerHTML = "";
    container.appendChild(tableEl);

    const initialData = getMonitorDataForTabulator();
    const columns = createMonitorColumns(initialData);

    monitorState.table = new Tabulator("#data-table", {
        columns: columns,
        data: transformMonitorDataForTabulator(initialData),
        height: "100%",
        layout: "fitColumns",
        placeholder: "No players available",
        rowHeight: monitorState.rowHeight
    });

    monitorState.table.on("cellClick", (e, cell) => {
        if (e.target.tagName === "A") {
            return false;
        }
        cell.getRow().toggleSelect();
    });

    monitorState.table.on("tableBuilt", function() {
        if (initialData && Object.keys(initialData).length > 0) {
            monitorState.table.setSort("id", "asc");
        }
    });

    return monitorState.table;
}

// ============================================================================
// Column Definitions
// ============================================================================

function createMonitorColumns(data) {
    const columns = [{
        formatter: "rowSelection",
        frozen: true,
        titleFormatter: "rowSelection",
        hozAlign: "center",
        headerSort: false,
        width: 45,
    }];

    // Get all unique fields from data
    const allFields = new Set();
    Object.values(data).forEach(playerData => {
        Object.keys(playerData).forEach(field => {
            if (field !== "pageOrder") {
                allFields.add(field);
            }
        });
    });

    // Sort fields by monitor priority
    const sortedFields = Array.from(allFields).sort((a, b) => {
        const ai = MONITOR_PRIORITY_FIELDS.indexOf(a);
        const bi = MONITOR_PRIORITY_FIELDS.indexOf(b);

        if (ai !== -1 && bi !== -1) return ai - bi;
        if (ai !== -1) return -1;
        if (bi !== -1) return 1;
        return a.localeCompare(b);
    });

    sortedFields.forEach((field) => {
        const column = {
            title: field,
            field: field,
            headerFilter: "input",
        };

        // Add special formatters for specific fields
        if (field === "id") {
            column.frozen = true;
            column.width = 70;
        } else if (field === "label") {
            column.frozen = true;
            column.width = 120;
        } else if (field === "player") {
            column.formatter = formatPlayerCell;
            column.frozen = true;
            column.width = 120;
        } else if (field === "page") {
            column.formatter = formatPageCell;
            column.width = 200;
        } else if (field === "progress") {
            column.formatter = formatProgressCell;
        } else if (field === "lastSeen") {
            column.formatter = formatLastSeenCell;
        }

        columns.push(column);
    });

    return columns;
}

// ============================================================================
// Cell Formatters
// ============================================================================

function formatPlayerCell(cell) {
    const value = cell.getValue();
    // data-uname attribute allows us to find this element for heartbeat updates
    return `<div class="d-flex align-items-center gap-2">
        <a class="link-subtle player-name" href="${uproot.vars.root}/p/${uproot.vars.sname}/${value}/" target="_blank">${value}</a>
        <span class="heartbeat" data-uname="${value}" aria-hidden="true">♥</span>
    </div>`;
}

function formatPageCell(cell) {
    const path = cell.getValue() || "";
    const slashIndex = path.lastIndexOf("/");
    let dir = "", nameExt = path;

    if (slashIndex !== -1) {
        dir = path.slice(0, slashIndex + 1);
        nameExt = path.slice(slashIndex + 1);
    }

    const dotIndex = nameExt.lastIndexOf(".");
    let name = nameExt, ext = "";

    if (dotIndex > 0) {
        name = nameExt.slice(0, dotIndex);
        ext = nameExt.slice(dotIndex);
    }

    let html = "";
    if (dir) html += `<span class="app">${dir}</span>`;
    html += `<span class="page">${name}</span>`;
    if (ext) html += `<span class="extension">${ext}</span>`;
    return html;
}

function formatProgressCell(cell) {
    const data = cell.getRow().getData();
    const tooltip = Array.isArray(data.pageOrder) && data.pageOrder.length > 0
        ? data.pageOrder.join(" → ")
        : "";
    return `<span title="${tooltip}">${cell.getValue()}</span>`;
}

function formatLastSeenCell(cell) {
    const value = cell.getValue();
    if (!value || value === "—") return value;
    if (value.length >= 8) {
        const hhmm = value.slice(-8, -3);
        const ss = value.slice(-3);
        return `<span title="${value}">${hhmm}<span class="text-secondary opacity-50">${ss}</span></span>`;
    }
    return value;
}

// ============================================================================
// Data Transformation
// ============================================================================

function getMonitorDataForTabulator() {
    const info = uproot.vars.info || {};
    const online = uproot.vars.online || {};
    const extraData = uproot.vars.extraData || {};

    const monitorData = {};
    const allPlayers = new Set([...Object.keys(info), ...Object.keys(extraData)]);

    for (const uname of allPlayers) {
        const tuple = info[uname];
        const id = tuple?.[0];
        const pageOrder = Array.isArray(tuple?.[1]) ? tuple[1] : [];
        const showPage = Number.isInteger(tuple?.[2]) ? tuple[2] : -1;
        const pageName = getPagePath(pageOrder, showPage);
        const lastSeen = online?.[uname] == null ? "—" : epochToLocalISO(online[uname]);

        monitorData[uname] = {
            id: { value_representation: id ?? "", time: 0, context: "system" },
            player: { value_representation: uname, time: 0, context: "system" },
            page: { value_representation: pageName, time: 0, context: "system" },
            progress: {
                value_representation: `${Math.max(0, showPage + 1)}/${Math.max(0, pageOrder.length)}`,
                time: 0,
                context: "system"
            },
            lastSeen: { value_representation: lastSeen, time: 0, context: "system" },
            pageOrder: pageOrder
        };

        // Add extra data fields
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
            if (field === "pageOrder") {
                row[field] = payload;
            } else {
                row[field] = payload.value_representation;
            }
        }

        transformedData.push(row);
    }

    return transformedData;
}

function getPagePath(pageOrder, showPage) {
    if (Array.isArray(pageOrder)) {
        if (Number.isInteger(showPage) && showPage >= 0 && showPage < pageOrder.length) {
            return pageOrder[showPage];
        }
        if (showPage === -1) return "Initialize.html";
    }
    return "End.html";
}

// ============================================================================
// Debounced Table Updates
// ============================================================================

/**
 * Schedules a debounced table update. Multiple rapid calls will result in
 * only one actual update after UPDATE_DEBOUNCE_MS of inactivity.
 */
function updateData() {
    if (monitorState.pendingUpdate) {
        clearTimeout(monitorState.pendingUpdate);
    }
    monitorState.pendingUpdate = setTimeout(() => {
        monitorState.pendingUpdate = null;
        doTableUpdate();
    }, UPDATE_DEBOUNCE_MS);
}

/**
 * Performs the actual table update. Called by the debounce mechanism.
 */
async function doTableUpdate() {
    // Keep Alpine store in sync with current data
    updateSessionStore();

    try {
        if (!monitorState.table) return;

        const tableHolder = document.getElementsByClassName("tabulator-tableholder")[0];
        if (!tableHolder) return;

        const scrollPosX = tableHolder.scrollLeft;
        const scrollPosY = tableHolder.scrollTop;

        const rawData = getMonitorDataForTabulator();
        const transformedData = transformMonitorDataForTabulator(rawData);
        const columns = createMonitorColumns(rawData);

        if (monitorState.table.initialized) {
            const currentColumnFields = monitorState.table.getColumnDefinitions().map(col => col.field);
            const newColumnFields = columns.map(col => col.field);

            if (JSON.stringify(currentColumnFields) !== JSON.stringify(newColumnFields)) {
                const currentSort = monitorState.table.getSorters();
                const selectedPlayers = getSelectedPlayers();

                createTable(monitorState.currentContainer);

                if (currentSort.length > 0 || selectedPlayers.length > 0) {
                    monitorState.table.on("tableBuilt", function() {
                        if (currentSort.length > 0) {
                            monitorState.table.setSort(currentSort);
                        }
                        restoreSelectedPlayers(selectedPlayers);
                    });
                }
            } else {
                const currentSort = monitorState.table.getSorters();
                const selectedPlayers = getSelectedPlayers();

                monitorState.table.setData(transformedData);

                if (currentSort.length > 0) {
                    monitorState.table.setSort(currentSort);
                }
                restoreSelectedPlayers(selectedPlayers);
            }

            tableHolder.scrollLeft = scrollPosX;
            tableHolder.scrollTop = scrollPosY;
        } else {
            monitorState.table.on("tableBuilt", function() {
                monitorState.table.setData(transformedData);
            });
        }
    } catch (error) {
        console.error("Error updating monitor data:", error);
        if (monitorState.table && monitorState.table.initialized) {
            monitorState.table.setData([]);
        }
    }
}

function restoreSelectedPlayers(selectedPlayers) {
    if (selectedPlayers.length === 0) return;

    selectedPlayers.forEach(player => {
        const rows = monitorState.table.searchRows("player", "=", player);
        if (rows.length > 0) {
            rows[0].select();
        }
    });
}

// ============================================================================
// Selection Helpers
// ============================================================================

function getSelectedPlayers(col = "player") {
    if (!monitorState.table || !monitorState.table.initialized) return [];
    return monitorState.table.getSelectedRows().map(row => row.getData()[col]);
}

// ============================================================================
// Multiview
// ============================================================================

function openMultiview() {
    const selectedIds = getSelectedPlayers("id");
    const count = selectedIds.length;

    if (count < 1) {
        uproot.error(_("No players selected."));
    } else if (count <= MAX_MULTIVIEW_PLAYERS) {
        const ids = selectedIds.sort().map(i => i.toString()).join(",");
        window.open(`./multiview/#${ids}`, "_blank");
    } else {
        uproot.error(
            _("Too many players selected (#n#). The maximum number of players that can be displayed in multiview is #m#.")
                .replace("#n#", count)
                .replace("#m#", MAX_MULTIVIEW_PLAYERS)
        );
    }
}

// ============================================================================
// Heartbeat Animation (CSS-only, no table re-render)
// ============================================================================

/**
 * Triggers a heartbeat animation for a player by directly manipulating the DOM.
 * This avoids expensive table re-renders - the heartbeat is just a CSS class toggle.
 */
function triggerHeartbeat(uname) {
    // Find the heartbeat element by data-uname attribute
    const heartbeatEl = document.querySelector(`.heartbeat[data-uname="${uname}"]`);
    if (!heartbeatEl) return;

    // Clear any existing timeout for this player
    if (monitorState.activeHeartbeats.has(uname)) {
        clearTimeout(monitorState.activeHeartbeats.get(uname));
    }

    // Add active class
    heartbeatEl.classList.add("active");

    // Schedule removal of active class
    const timeoutId = setTimeout(() => {
        heartbeatEl.classList.remove("active");
        monitorState.activeHeartbeats.delete(uname);
    }, HEARTBEAT_DURATION_MS);

    monitorState.activeHeartbeats.set(uname, timeoutId);
}

// ============================================================================
// Event Handlers
// ============================================================================

uproot.onCustomEvent("FieldChanged", (event) => {
    const [pid, field, value] = event.detail;
    const data = {
        [pid[2]]: { [field]: value.data }
    };
    reshapeAndUpdateExtraData(data);
});

uproot.onCustomEvent("Attended", (event) => {
    const uname = event?.detail?.uname;
    const info = event?.detail?.info;

    if (!uname || !Array.isArray(info)) return;

    if (!uproot.vars.info) uproot.vars.info = {};
    if (!uproot.vars.online) uproot.vars.online = {};

    uproot.vars.info[uname] = info;
    uproot.vars.online[uname] = Date.now() / 1000;

    // Debounced table update (also updates Alpine store counts)
    updateData();

    // Heartbeat animation via direct DOM manipulation (no re-render needed)
    // Small delay to ensure the row exists if this is a new player
    setTimeout(() => triggerHeartbeat(uname), 50);
});

// ============================================================================
// Window API (for cross-file and modal communication)
// ============================================================================

/**
 * Updates the monitor with new info/online data from the server.
 */
window.newInfoOnline = function(data) {
    if (!uproot) return;
    uproot.vars.online = data.online || {};
    uproot.vars.info = data.info || {};

    // Debounced table update (also updates Alpine store counts)
    updateData();
};

/**
 * Merges extra data fields into uproot.vars.extraData and refreshes the table.
 */
window.updateExtraData = function(extraDataObj) {
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

/**
 * Invokes a command on the server for the selected players.
 */
window.invokeFromMonitor = function(fname, ...args) {
    return uproot.invoke(
        fname,
        uproot.vars.sname,
        getSelectedPlayers(),
        ...args
    );
};

/**
 * Opens a modal for player management actions.
 */
window.mmodal = function(modalName) {
    const selected = getSelectedPlayers();
    const modal = window.bootstrap?.Modal.getOrCreateInstance(I(`${modalName}-modal`));

    if (selected.length > 0) {
        // Update Alpine store with selected player count
        if (window.Alpine && Alpine.store("session")) {
            Alpine.store("session").selectedCount = selected.length;
        }
        modal?.show();
    } else {
        uproot.error("No players selected.");
    }
};

// ============================================================================
// Modal Action Handlers
// ============================================================================

window.actuallyManage = function() {
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

window.actuallyInsert = function() {
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

window.actuallyAdminmessageSend = function() {
    const msg = I("adminmsg")?.value ?? "";

    window.bootstrap?.Modal.getOrCreateInstance(I("adminmessage_send-modal")).hide();
    window.invokeFromMonitor("adminmessage", msg).then(() => {
        uproot.alert("The action has completed.");
    });
};

window.actuallyRedirect = function() {
    const url = I("redirect-url")?.value ?? "";

    if (!url.startsWith("http://") && !url.startsWith("https://")) {
        return uproot.error("URL must start with http:// or https://");
    }

    window.bootstrap?.Modal.getOrCreateInstance(I("redirect-modal")).hide();
    window.invokeFromMonitor("redirect", url).then(() => {
        uproot.alert("The action has completed.");
    });
};

window.actuallyGroup = function() {
    const action = uproot.selectedValue("group_action");

    if (!action) {
        return uproot.error(_("No action selected."));
    }

    const groupSize = parseInt(I("group-size")?.value ?? "2", 10);
    const shuffle = !!I("group-shuffle")?.checked;
    const reload = !!I("group-reload")?.checked;

    if (action === "by_size" && (isNaN(groupSize) || groupSize < 1)) {
        return uproot.error(_("Group size must be at least 1."));
    }

    window.bootstrap?.Modal.getOrCreateInstance(I("group-modal")).hide();
    window.invokeFromMonitor("group_players", { action, group_size: groupSize, shuffle, reload })
        .then((result) => {
            loadExtraData();
            if (result.groups_created) {
                uproot.alert(_("Created #n# group(s).").replace("#n#", result.groups_created));
            } else if (result.players_reset !== undefined) {
                uproot.alert(_("Reset group assignment for #n# player(s).").replace("#n#", result.players_reset));
            } else {
                uproot.alert(_("The action has completed."));
            }
        })
        .catch((err) => {
            uproot.error(err.message || _("An error occurred."));
        });
};
