/**
 * Admin dashboard utilities for rendering rooms, sessions, and configs.
 */

const ui = uproot.vars._uproot_internal;

// ============================================================================
// Date/Time Utilities
// ============================================================================

function epochToLocalDateTime(epochSeconds) {
    return new Date(epochSeconds * 1000).toLocaleString();
}

function epochToLocalISO(epochSeconds) {
    const d = new Date(epochSeconds * 1000);
    const pad = (n) => String(n).padStart(2, "0");
    return (
        String(d.getFullYear()).padStart(4, "0") + "-" +
        pad(d.getMonth() + 1) + "-" +
        pad(d.getDate()) + ", " +
        pad(d.getHours()) + ":" +
        pad(d.getMinutes()) + ":" +
        pad(d.getSeconds())
    );
}

// ============================================================================
// DOM Helper Functions
// ============================================================================

/**
 * Creates an element with the given tag, className, and optional attributes.
 */
function createElement(tag, className, attrs = {}) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    Object.entries(attrs).forEach(([key, value]) => {
        if (key === "textContent") {
            el.textContent = value;
        } else if (key === "innerHTML") {
            el.innerHTML = value; // SAFE - only used with sanitized content
        } else {
            el.setAttribute(key, value);
        }
    });
    return el;
}

/**
 * Creates a table row with label and value for d-table layout.
 */
function createTableRow(label, value, options = {}) {
    const {
        valueIsLink = false,
        linkHref = "",
        isMonospace = false,
        isNA = false
    } = options;

    const row = createElement("div", "d-table-row");

    const labelSpan = createElement("span",
        "d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase",
        { textContent: label }
    );

    let valueClass = "d-table-cell w-100";
    if (isNA) valueClass += " text-body-tertiary";
    if (isMonospace) valueClass += " font-monospace";

    const valueSpan = createElement("span", valueClass);

    if (valueIsLink && linkHref) {
        valueSpan.innerHTML = `<a class="link-subtle" href="${linkHref}">${encodeURIComponent(value)}</a>`; // SAFE
    } else {
        valueSpan.textContent = value;
    }

    row.appendChild(labelSpan);
    row.appendChild(valueSpan);
    return row;
}

/**
 * Creates a badge element.
 */
function createBadge(text, className) {
    return createElement("div", className, { textContent: text });
}

// ============================================================================
// URL Helpers
// ============================================================================

/**
 * Constructs an admin area URL for a given resource type and name.
 */
function adminUrl(type, name) {
    return `${uproot.vars.root}/admin/${type}/${encodeURIComponent(name)}/`;
}

/**
 * Constructs a URL for creating a new session with a given config.
 */
function newSessionUrl(config) {
    return `${uproot.vars.root}/admin/sessions/new/?config=${encodeURIComponent(config)}`;
}

// ============================================================================
// Room Rendering
// ============================================================================

function renderRooms(rooms, containerId) {
    const container = I(containerId);
    const sortedRooms = Object.values(rooms).sort((a, b) => a.name.localeCompare(b.name));

    if (sortedRooms.length > 0) {
        container.innerHTML = ""; // SAFE
    }

    sortedRooms.forEach(room => {
        const col = createElement("div", "col mb-4");
        const card = createElement("div", "border-uproot-light card");

        // Card header
        const cardHeader = createElement("div", "bg-white border-0 card-header");
        const headerContent = createElement("div",
            "align-items-center border-bottom border-uproot-light d-flex justify-content-between pb-2 pt-1 text-uproot"
        );

        const title = createElement("h5", "fw-semibold mb-1 me-3 text-nowrap");
        const roomUrl = adminUrl("room", room.name);
        title.innerHTML = `<a class="link-offset-2 link-underline-opacity-0 link-underline-opacity-100-hover link-underline-uproot text-uproot" href="${roomUrl}"><span class="font-monospace">${encodeURIComponent(room.name)}</span> <i class="font-bi">&#xF891;</i></a>`; // SAFE

        const statusBadge = createBadge(
            room.open ? _("room is Open") : _("Closed"),
            room.open
                ? "badge bg-success border border-success my-1"
                : "badge border border-danger my-1 text-danger"
        );

        const rightCol = createElement("div", "");
        rightCol.appendChild(statusBadge);

        headerContent.appendChild(title);
        headerContent.appendChild(rightCol);
        cardHeader.appendChild(headerContent);
        card.appendChild(cardHeader);

        // Card body
        const cardBody = createElement("div",
            "bg-white card-body d-flex justify-content-between pb-1 pt-1 rounded-bottom"
        );

        const leftCol = createElement("div", "col d-table mb-2");

        // Session row
        if (room.sname) {
            const sessionUrl = adminUrl("session", room.sname);
            leftCol.appendChild(createTableRow(_("Session"), room.sname, {
                valueIsLink: true,
                linkHref: sessionUrl,
                isMonospace: true
            }));
        } else {
            leftCol.appendChild(createTableRow(_("Session"), _("N/A"), { isNA: true }));
        }

        // Config row
        leftCol.appendChild(createTableRow(
            _("Config"),
            room.config || _("N/A"),
            { isMonospace: !!room.config, isNA: !room.config }
        ));

        // Labels row
        const labelsRow = createElement("div", "d-table-row");
        if (room.labels != null && room.labels.length > 0) {
            labelsRow.innerHTML = `<span class="d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase">${_("Labels")}</span> <span class="d-table-cell w-100">${room.labels.length}</span>`; // SAFE
            labelsRow.title = room.labels.slice(0, 5).join(", ") + (room.labels.length > 5 ? "..." : "");
        } else {
            labelsRow.innerHTML = `<span class="d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase">${_("Labels")}</span> <span class="d-table-cell text-body-tertiary w-100">N/A</span>`; // SAFE
        }
        leftCol.appendChild(labelsRow);

        // Join mode row
        const freejoin = room.labels == null && room.capacity == null;
        const freejoinRow = createElement("div", "d-table-row");
        freejoinRow.innerHTML = `<span class="d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase">${_("Join mode")}</span> <span class="d-table-cell w-100">${freejoin ? _("free join") : _("restricted")}</span>`; // SAFE
        leftCol.appendChild(freejoinRow);

        cardBody.appendChild(leftCol);

        // Capacity badges
        const badges = createElement("div", "align-items-end d-flex flex-column justify-content-center");

        let nPlayers = 0;
        if (room.sname && uproot.vars.sessions[room.sname]) {
            nPlayers = uproot.vars.sessions[room.sname].n_players;
        }

        // Capacity badge
        const capacityBadge = createElement("div", "");
        if (room.capacity != null) {
            const fillRatio = nPlayers / room.capacity;
            if (room.open) {
                capacityBadge.className = fillRatio >= 1
                    ? "badge bg-success border border-success mb-2"
                    : fillRatio >= 0.9
                        ? "badge bg-warning border border-warning mb-2 text-dark"
                        : "badge bg-danger border border-danger mb-2";
            } else {
                capacityBadge.className = "badge border border-danger mb-2 text-danger";
            }
            capacityBadge.textContent = `${_("Capacity")}: ${room.capacity}`;
        } else {
            capacityBadge.className = room.open
                ? "badge bg-success border border-success mb-2"
                : "badge border border-success mb-2 text-success";
            capacityBadge.textContent = _("Capacity") + ": ∞";
        }
        badges.appendChild(capacityBadge);

        // Players badge
        if (room.sname && uproot.vars.sessions[room.sname]) {
            const nPlayersBadge = createElement("div", "");
            if (room.capacity != null) {
                const fillRatio = nPlayers / room.capacity;
                nPlayersBadge.className = fillRatio >= 1
                    ? "badge bg-success border border-success mb-2"
                    : fillRatio >= 0.9
                        ? "badge bg-warning border border-warning mb-2 text-dark"
                        : "badge bg-danger border border-danger mb-2";
            } else {
                nPlayersBadge.className = "badge bg-success border border-success mb-2";
            }
            nPlayersBadge.textContent = `${_("Players")}: ${nPlayers}`;
            badges.appendChild(nPlayersBadge);
        }

        if (badges.children.length > 0) {
            cardBody.appendChild(badges);
        }

        if (cardBody.children.length > 0) {
            card.appendChild(cardBody);
        }

        col.appendChild(card);
        container.appendChild(col);
    });
}

// ============================================================================
// Session Rendering
// ============================================================================

function renderSessions(sessions, containerId) {
    const container = I(containerId);
    const sortedSessions = Object.values(sessions).sort((a, b) => (b.started || 0) - (a.started || 0));

    if (sortedSessions.length > 0) {
        container.innerHTML = ""; // SAFE
    }

    sortedSessions.forEach(session => {
        const col = createElement("div", "col mb-4");
        const card = createElement("div", "card");

        // Card header
        const cardHeader = createElement("div", "bg-white border-0 card-header");
        const headerContent = createElement("div",
            "align-items-center border-bottom border-uproot-light d-flex justify-content-between pb-2 pt-1"
        );

        if (session.sname) {
            const title = createElement("h5", "d-inline-block fw-semibold mb-1 me-3 text-nowrap");
            const sessionUrl = adminUrl("session", session.sname);
            title.innerHTML = `<a class="link-dark link-offset-2 link-underline-opacity-0 link-underline-opacity-100-hover link-underline-opacity-0" href="${sessionUrl}"><span class="font-monospace">${encodeURIComponent(session.sname)}</span> <i class="font-bi">&#xF8A7;</i></a>`; // SAFE
            headerContent.appendChild(title);
        }

        if (session.started) {
            const time = createElement("small",
                "badge border border-opacity-0 border-white fw-normal px-0 my-1 text-body-tertiary",
                { textContent: `${_("Started")}: ${epochToLocalDateTime(session.started)}` }
            );
            headerContent.appendChild(time);
        }

        cardHeader.appendChild(headerContent);

        // Card body
        const cardBody = createElement("div",
            "bg-white card-body d-flex flex-row justify-content-between pb-2 pt-0 rounded-bottom"
        );

        const infoTable = createElement("div", "d-table mb-2 mt-1");

        // Room row
        if (session.room) {
            const roomUrl = adminUrl("room", session.room);
            infoTable.appendChild(createTableRow(_("Room"), session.room, {
                valueIsLink: true,
                linkHref: roomUrl,
                isMonospace: true
            }));
        } else {
            infoTable.appendChild(createTableRow(_("Room"), _("N/A"), { isNA: true }));
        }

        // Config row
        infoTable.appendChild(createTableRow(
            _("Config"),
            session.config || _("N/A"),
            { isMonospace: !!session.config, isNA: !session.config }
        ));

        // Description row
        infoTable.appendChild(createTableRow(
            _("Description"),
            session.description || _("N/A"),
            { isNA: !session.description }
        ));

        cardBody.appendChild(infoTable);

        // Badges
        const badges = createElement("div", "align-items-end d-flex flex-column justify-content-center");

        if (session.n_players != null) {
            badges.appendChild(createBadge(
                `${_("Players")}: ${session.n_players}`,
                "badge bg-uproot border border-uproot mb-2"
            ));
        }

        if (session.n_groups != null) {
            badges.appendChild(createBadge(
                `${_("Groups")}: ${session.n_groups}`,
                "badge bg-white border border-uproot ms-2 text-uproot"
            ));
        }

        if (badges.children.length > 0) {
            cardBody.appendChild(badges);
        }

        card.appendChild(cardHeader);
        if (cardBody.children.length > 0) {
            card.appendChild(cardBody);
        }

        col.appendChild(card);
        container.appendChild(col);
    });
}

// ============================================================================
// Config/App Rendering
// ============================================================================

function renderConfigsApps(data, containerId) {
    const container = I(containerId);

    const select = createElement("select", "form-select", {
        id: "configs-apps-select",
        name: "config"
    });

    select.addEventListener("change", (e) => {
        if (typeof configSelected !== "undefined") {
            configSelected(e.target.value);
        }
    });

    ["configs", "apps"].forEach(groupKey => {
        if (!data[groupKey]) return;

        const optgroup = createElement("optgroup", "", {
            label: groupKey.charAt(0).toUpperCase() + groupKey.slice(1)
        });

        Object.entries(data[groupKey]).forEach(([key, value]) => {
            if (key == null) return;

            const displayKey = key.startsWith("~") ? key.substring(1) : key;
            const option = createElement("option", "", { value: key });
            option.textContent = (value != null && value !== "")
                ? `${displayKey}: ${value}`
                : displayKey;

            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);
    });

    container.appendChild(select);

    const label = createElement("label", "", {
        for: "configs-apps-select",
        textContent: _("Config or app")
    });
    label.htmlFor = "configs-apps-select";
    container.appendChild(label);

    return select;
}

function renderConfigsAppsCards(data, containerId, groupKey) {
    const container = I(containerId);
    if (!data[groupKey]) return;

    const card = createElement("div", "card mb-3");

    const cardBodyClass = groupKey === "configs"
        ? "bg-light card-body px-3 py-2 rounded"
        : "card-body px-3 py-2";
    const cardBody = createElement("div", cardBodyClass);

    const listGroup = createElement("div", "list-group list-group-flush");

    Object.entries(data[groupKey]).forEach(([key, value]) => {
        if (key == null) return;

        const item = createElement("div",
            "align-items-center bg-transparent d-flex justify-content-between list-group-item p-0"
        );

        const content = createElement("div", "");
        const displayKey = key.startsWith("~") ? key.substring(1) : key;

        const title = createElement("div", "font-monospace fw-semibold h5 my-2", {
            textContent: displayKey
        });
        content.appendChild(title);

        if (value != null && value !== "") {
            const desc = createElement("div", "d-table mb-2");
            const descLabel = createElement("div",
                "d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase",
                { textContent: key.startsWith("~") ? _("Description") : _("Apps") }
            );
            const descContent = createElement("div",
                key.startsWith("~") ? "d-table-cell w-100" : "d-table-cell font-monospace w-100",
                { textContent: value }
            );
            desc.appendChild(descLabel);
            desc.appendChild(descContent);
            content.appendChild(desc);
        }

        item.appendChild(content);

        const detailsLink = createElement("a", "btn btn-sm btn-outline-uproot btn-launch", {
            href: newSessionUrl(key),
            title: _("New session")
        });
        detailsLink.innerHTML = `<span class="font-bi fs-3">&#xF4FA;</span>`; // SAFE
        item.appendChild(detailsLink);

        listGroup.appendChild(item);
    });

    cardBody.appendChild(listGroup);
    card.appendChild(cardBody);
    container.appendChild(card);
}

// ============================================================================
// Citation
// ============================================================================

function showBibTeX() {
    uproot.alert(`<h5 class="mb-3">${_("Pre-formatted citation")} <span class="fw-light">(Chicago style)</span></h5>
<p class="mb-4">Grossmann, Max&nbsp;R.&nbsp;P., and Holger Gerhardt. 2025. “uproot: An Experimental Framework with a Focus on Performance, Flexibility, and Ease of Use.” Unpublished manuscript.</p>
<h5 class="mb-3">BibTeX entry</h5>
<code class="text-uproot">
<b>@unpublished</b>{<b>uproot</b>,<br>
&nbsp;&nbsp;<b>author</b> = {Grossmann, Max~R.~P. and Gerhardt, Holger},<br>
&nbsp;&nbsp;<b>title</b>&nbsp;= {uproot: An Experimental Framework with a~Focus on Performance, Flexibility, and Ease of Use},<br>
&nbsp;&nbsp;<b>year</b>&nbsp;= {2026},<br>
&nbsp;&nbsp;<b>note</b>&nbsp;= {Unpublished manuscript}<br>
}
</code>`);
}
