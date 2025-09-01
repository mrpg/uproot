const ui = uproot.vars._uproot_internal;

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

function renderRooms(rooms, containerId) {
    const container = I(containerId);
    const sortedRooms = Object.values(rooms).sort((a, b) => a.name.localeCompare(b.name));

    if (sortedRooms.length > 0) {
        container.innerHTML = "";  // SAFE
    }

    sortedRooms.forEach(room => {
        const col = document.createElement("div");
        col.className = "col";
        const card = document.createElement("div");
        card.className = "border-uproot-light card col mb-3";

        // Card header with room name and status

        const cardHeader = document.createElement("div");
        cardHeader.className = "align-items-center bg-uproot-light border-uproot-light card-header d-flex justify-content-between py-2 text-uproot";

        const headerContent = document.createElement("div");
        const title = document.createElement("h5");
        title.className = "fw-semibold font-monospace mb-0 me-3";
        title.innerHTML =  // SAFE
            `<a class="link-offset-2 link-underline-opacity-0 link-underline-opacity-100-hover link-underline-uproot text-uproot" href="${uproot.vars.root}/admin/room/${encodeURIComponent(room.name)}"><span class="font-monospace">${encodeURIComponent(room.name)}</span> <i class="font-bi">&#xF891;</i></a>`;  // bi-house-gear
        headerContent.appendChild(title);

        const rightCol = document.createElement("div");
        //rightCol.className = "text-end";
        const statusBadge = document.createElement("span");
        statusBadge.className =
            room.start ? "badge bg-success border border-success my-1" : "badge border border-danger my-1 text-danger";
        statusBadge.textContent = room.start ? _("Started") : _("Inactive");
        rightCol.appendChild(statusBadge);

        headerContent.appendChild(rightCol);
        cardHeader.appendChild(headerContent);
        card.appendChild(cardHeader);

        // Card body with config, session info, and links

        const cardBody = document.createElement("div");
        cardBody.className = "bg-light card-body d-flex justify-content-between pb-1 pt-3 rounded-bottom";

        // Left column for config and session info

        const leftCol = document.createElement("div");
        leftCol.className = "col d-table mb-2";

        const sessionItem = document.createElement("div");
        sessionItem.className = "d-table-row";
        const sessionLabel = document.createElement("span");
        sessionLabel.className = "d-table-cell fw-semibold pe-3 text-nowrap";
        sessionLabel.textContent = `${_("Session")} `;
        const sessionValue = document.createElement("span");
        if (room.sname) {
            sessionValue.className = "d-table-cell font-monospace";
            sessionValue.innerHTML =  // SAFE
                `<a class="link-subtle" href="${uproot.vars.root}/admin/session/${encodeURIComponent(room.sname)}">${encodeURIComponent(room.sname)}</a>`
        } else {
            sessionValue.className = "d-table-cell text-body-tertiary";
            sessionValue.textContent = _("N/A");
        }
        sessionItem.appendChild(sessionLabel);
        sessionItem.appendChild(sessionValue);
        leftCol.appendChild(sessionItem);

        const configItem = document.createElement("div");
        configItem.className = "d-table-row";
        const configLabel = document.createElement("span");
        configLabel.className = "d-table-cell fw-semibold pe-3 text-nowrap";
        configLabel.textContent = `${_("Config")} `;
        const configValue = document.createElement("span");
        if (room.config) {
            configValue.textContent = room.config;
            configValue.className = "d-table-cell font-monospace w-100";
        } else {
            configValue.textContent = _("N/A");
            configValue.className = "d-table-cell text-body-tertiary";
        }
        configItem.appendChild(configLabel);
        configItem.appendChild(configValue);
        leftCol.appendChild(configItem);

        const labelsItem = document.createElement("div");
        labelsItem.className = "d-table-row";
        if (room.labels != null && room.labels.length > 0) {
            labelsItem.innerHTML =  // SAFE
                `<span class="d-table-cell fw-semibold pe-3 text-nowrap">${_("Labels")}</span> <span class="d-table-cell">${room.labels.length}</span>`;
            labelsItem.title = room.labels.slice(0, 5).join(", ") + (room.labels.length > 5 ? "..." : "");
        } else{
            labelsItem.innerHTML =  // SAFE
                `<span class="d-table-cell fw-semibold pe-3 text-nowrap">${_("Labels")}</span> <span class="d-table-cell text-body-tertiary">N/A</span>`;
        }
        leftCol.appendChild(labelsItem);

        const freejoin = room.labels == null && room.capacity == null;
        const freejoinItem = document.createElement("div");
        freejoinItem.className = "d-table-row";
        if (freejoin) {
            freejoinItem.innerHTML =  // SAFE
                `<span class="d-table-cell fw-semibold pe-3 text-nowrap">${_("Join mode")}</span> <span class="d-table-cell">${_("free join")}</span>`;
        } else {
            freejoinItem.innerHTML =  // SAFE
                `<span class="d-table-cell fw-semibold pe-3 text-nowrap">${_("Join mode")}</span> <span class="d-table-cell">${_("restricted")}</span>`;
        }
        leftCol.appendChild(freejoinItem);

        cardBody.appendChild(leftCol);

        // Middle column for links

        const links = document.createElement("div");
        links.className = "d-flex flex-column justify-content-center";

        /*
        if (room.sname) {
            const sessionLink = document.createElement("a");
            sessionLink.href = `${uproot.vars.root}/admin/session/${encodeURIComponent(room.sname)}/`;
            sessionLink.className = "btn btn-sm btn-outline-uproot btn-view-details d-block me-2 py-0";
            sessionLink.innerHTML = "&boxbox;";  // SAFE
            sessionLink.title = _("View session");
            links.appendChild(sessionLink);
        } else {
            const sessionLink = document.createElement("button");
            sessionLink.disabled = true;
            sessionLink.className = "btn btn-sm btn-view-details d-block me-2 py-0 opacity-25";
            sessionLink.innerHTML = "&boxbox;";  // SAFE
            links.appendChild(sessionLink);
        }
            */

        /*
        const joinLink = document.createElement("a");
        joinLink.href = `${uproot.vars.root}/admin/room/${encodeURIComponent(room.name)}/`;
        //joinLink.setAttribute("target", "_blank");
        joinLink.className = "btn btn-sm btn-outline-uproot btn-view-details";
        joinLink.innerHTML = "&rarr;";  // SAFE
        joinLink.title = _("View room");
        links.appendChild(joinLink);
        */
        /*
        const joinLink = document.createElement("a");
        joinLink.href = `${uproot.vars.root}/room/${encodeURIComponent(room.name)}/`;
        joinLink.setAttribute("target", "_blank");
        joinLink.className = "fs-sm fw-bolder link-danger link-offset-2 link-underline-danger link-underline-opacity-0 link-underline-opacity-100-hover";
        joinLink.textContent = _("Enter room as a participant");
        joinLink.title = _("Enter room as a participant");
        links.appendChild(joinLink);
        */

        cardBody.appendChild(links);

        // Right column for capacity badges

        const badges = document.createElement("div");
        badges.className = "align-items-end col d-flex flex-column justify-content-center";
        const badgesRow1 = document.createElement("div");
        badgesRow1.className = "mb-2";

        var n_players = 0
        if (room.sname && uproot.vars.sessions[room.sname]) {
            n_players = uproot.vars.sessions[room.sname].n_players;
        }

        const capacityBadge = document.createElement("span");
        if (room.capacity != null) {
            if (room.start) {
                // If session is full, show as success, otherwise warning
                capacityBadge.className =
                    n_players < room.capacity ? "badge bg-warning border border-warning text-dark" : "badge bg-success border border-success";
                // If session is less than 90% full, show as danger
                capacityBadge.className =
                    n_players < 0.9 * room.capacity ? "badge bg-danger border border-danger" : "badge bg-warning border border-warning";
            } else {
                capacityBadge.className = "badge border border-danger ms-2 text-danger"
            }
            capacityBadge.textContent = `${_("Capacity")}: ${room.capacity}`;
        } else {
            if (room.start) {
                capacityBadge.className = "badge bg-success border border-success";
                capacityBadge.textContent = _("Capacity") + ": ∞";
            } else {
                capacityBadge.className = "badge border border-success text-success";
                capacityBadge.textContent = _("Capacity") + ": ∞";
            }
        }
        badgesRow1.appendChild(capacityBadge);

        const badgesRow2 = document.createElement("div");
        badgesRow2.className = "mb-2";

        const nPlayersBadge = document.createElement("span");
        if (room.sname && uproot.vars.sessions[room.sname]) {
            if (room.capacity != null) {
                // If session is full, show as success, otherwise warning
                nPlayersBadge.className =
                    n_players < room.capacity ? "badge bg-warning border border-warning ms-2 text-dark" : "badge bg-success boder border-success";
                // If session is less than 90% full, show as danger
                nPlayersBadge.className =
                    n_players < 0.9 * room.capacity ? "badge bg-danger border border-danger ms-2" : "badge bg-warning border border-warning ms-2";
                nPlayersBadge.textContent = `${_("Players")}: ${n_players}`;
            } else {
                nPlayersBadge.className = "badge bg-success border border-success ms-2";
                nPlayersBadge.textContent = `${_("Players")}: ${n_players}`;
            }
        } else {
            nPlayersBadge.className = room.start ? "badge bg-danger border border-danger ms-2" : "badge border border-danger ms-2 text-danger";
            nPlayersBadge.textContent = `${_("Players")}: 0`;
        }
        badgesRow2.appendChild(nPlayersBadge);

        badges.appendChild(badgesRow1)
        badges.appendChild(badgesRow2)

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

function renderSessions(sessions, containerId) {
    const container = I(containerId);
    const sortedSessions = Object.values(sessions).sort((a, b) => (b.started || 0) - (a.started || 0));

    if (sortedSessions.length > 0) {
        container.innerHTML = "";  // SAFE
    }

    sortedSessions.forEach(session => {
        const col = document.createElement("div");
        col.className = "col";
        const card = document.createElement("div");
        card.className = "border-uproot-light card mb-3";

        const cardHeader = document.createElement("div");
        cardHeader.className = "bg-uproot-light border-uproot-light card-header py-1";

        const headerContent = document.createElement("div");
        headerContent.className = "align-items-center d-flex justify-content-between"

        if (session.sname) {
            const title = document.createElement("h5");
            title.className = "d-inline-block fw-semibold font-monospace mb-2 me-5 mt-1";
            title.innerHTML =  // SAFE
                `<a class="link-dark link-offset-2 link-underline-opacity-0 link-underline-opacity-100-hover link-underline-opacity-0" href="${uproot.vars.root}/admin/session/${encodeURIComponent(session.sname)}/"><span class="font-monospace">${encodeURIComponent(session.sname)}</span> <i class="font-bi">&#xF8A7;</i></a>`  // bi-person-gear
            headerContent.appendChild(title);
        }

        if (session.started) {
            const time = document.createElement("small");
            time.className = "text-body-tertiary";
            time.textContent = `${_("Started")}: ` + epochToLocalDateTime(session.started);
            headerContent.appendChild(time);
        }

        cardHeader.appendChild(headerContent);

        /*
        if (session.sname) {
            const detailsLink = document.createElement("a");
            detailsLink.href = `${uproot.vars.root}/admin/session/${encodeURIComponent(session.sname)}/`;
            detailsLink.className = "btn btn-sm btn-outline-uproot btn-view-details py-0";
            detailsLink.innerHTML = "&boxbox;";  // SAFE
            detailsLink.title = _("View session details");
            cardHeader.appendChild(detailsLink);
        }
        */

        const cardBody = document.createElement("div");
        cardBody.className = "bg-light card-body d-flex flex-row justify-content-between pb-2 pt-2 rounded-bottom";

        const configRoomItem = document.createElement("div");
        configRoomItem.className = "d-table mb-2 mt-1";
        const roomItem = document.createElement("div");
        roomItem.className = "d-table-row";
        const roomLabel = document.createElement("span");
        roomLabel.className = "d-table-cell fw-semibold pe-3 text-nowrap";
        roomLabel.textContent = `${_("Room")} `;
        const roomValue = document.createElement("span");
        if (session.room) {
            roomValue.innerHTML =  // SAFE
                `<a class="link-subtle" href="${uproot.vars.root}/admin/room/${encodeURIComponent(session.room)}/">${encodeURIComponent(session.room)}</a>`;
            roomValue.className = "d-table-cell font-monospace w-100";
        } else {
            roomValue.textContent = _("N/A");
            roomValue.className = "d-table-cell text-body-tertiary w-100";
        }
        roomItem.appendChild(roomLabel)
        roomItem.appendChild(roomValue)
        configRoomItem.appendChild(roomItem);
        const configItem = document.createElement("div");
        configItem.className = "d-table-row";
        const configLabel = document.createElement("span");
        configLabel.className = "d-table-cell fw-semibold pe-3 text-nowrap";
        configLabel.textContent = `${_("Config")} `;
        const configValue = document.createElement("span");
        if (session.config) {
            configValue.textContent = session.config;
            configValue.className = "d-table-cell font-monospace w-100";
        } else {
            configValue.textContent = _("N/A");
            configValue.className = "d-table-cell text-body-tertiary w-100";
        }
        configItem.appendChild(configLabel);
        configItem.appendChild(configValue);
        configRoomItem.appendChild(configItem);

        const descItem = document.createElement("div");
        descItem.className = "d-table-row";
        const descLabel = document.createElement("span");
        descLabel.className = "d-table-cell fw-semibold pe-3 text-nowrap";
        descLabel.textContent = `${_("Description")} `;
        const descValue = document.createElement("span");
        if (session.description) {
            descValue.className = "d-table-cell w-100";
            descValue.textContent = session.description;
        } else {
            descValue.className = "d-table-cell text-body-tertiary w-100";
            descValue.textContent = _("N/A");

        }
        descItem.appendChild(descLabel);
        descItem.appendChild(descValue);

        configRoomItem.appendChild(descItem)

        cardBody.appendChild(configRoomItem);

        const badges = document.createElement("div");
        badges.className = "";

        /*
        if (session.room) {
            const badge = document.createElement("span");
            badge.className = "badge bg-uproot-light border border-uproot mb-1 me-2 text-uproot";
            badge.textContent = `${_("Room")}: ` + session.room;
            badges.appendChild(badge);
        }
        */

        if (session.n_players != null) {
            const badge = document.createElement("span");
            badge.className = "badge bg-uproot border border-uproot mb-1 me-2 mt-2";
            badge.textContent = session.n_players + " players";
            badges.appendChild(badge);
        }

        if (session.n_groups != null) {
            const badge = document.createElement("span");
            badge.className = "badge bg-white border border-uproot me-0 text-uproot";
            badge.textContent = session.n_groups + " groups";
            badges.appendChild(badge);
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

function renderConfigsApps(data, containerId) {
    const container = I(containerId);

    const select = document.createElement("select");
    select.className = "form-select";
    select.id = "configs-apps-select";
    select.name = "config";

    ["configs", "apps"].forEach(groupKey => {
        if (!data[groupKey]) return;

        const optgroup = document.createElement("optgroup");
        optgroup.label = groupKey.charAt(0).toUpperCase() + groupKey.slice(1);

        Object.entries(data[groupKey]).forEach(([key, value]) => {
            if (key == null) return;

            const option = document.createElement("option");
            const key_ = key.startsWith("~") ? key.substr(1) : key;

            option.value = key;

            if (value != null && value !== "") {
                option.textContent = `${key_}: ${value}`;
            } else {
                option.textContent = key_;
            }

            optgroup.appendChild(option);
        });

        select.appendChild(optgroup);
    });

    container.appendChild(select);
    container.innerHTML +=  // SAFE
        "<label for='configs-apps-select'>" + _("Config or app") + "</label>";
}

function renderConfigsAppsCards(data, containerId, groupKey) {
    const container = I(containerId);
    if (!data[groupKey]) return;

    const card = document.createElement("div");
    card.className = "card mb-3";

    const cardBody = document.createElement("div");
    if (groupKey === "configs") {
        cardBody.className = "bg-light card-body px-3 py-2 rounded";
    } else {
        cardBody.className = "card-body px-3 py-2";
    }

    const listGroup = document.createElement("div");
    listGroup.className = "list-group list-group-flush";

    Object.entries(data[groupKey]).forEach(([key, value]) => {
        if (key == null) return;

        const item = document.createElement("div");
        item.className = "align-items-center bg-transparent d-flex justify-content-between list-group-item p-0 py-1";

        const content = document.createElement("div");
        const key_ = key.startsWith("~") ? key.substr(1) : key;

        const title = document.createElement("div");
        title.className = "fw-semibold h5 font-monospace";
        title.textContent = key_;
        content.appendChild(title);

        if (value != null && value !== "") {
            const desc = document.createElement("div");
            //desc.className = "text-body-tertiary";
            desc.textContent = value;
            content.appendChild(desc);
        }

        item.appendChild(content);

        const detailsLink = document.createElement("a");
        detailsLink.href = `${uproot.vars.root}/admin/sessions/new/?config=${encodeURIComponent(key)}`;
        detailsLink.className = "btn btn-sm btn-outline-uproot btn-launch";
        detailsLink.innerHTML = `<span class="font-bi">&#xF4FA;</span>`;  // bi-plus-circle  // SAFE
        detailsLink.title = _("New session");
        item.appendChild(detailsLink);

        listGroup.appendChild(item);
    });

    cardBody.appendChild(listGroup);
    card.appendChild(cardBody);
    container.appendChild(card);
}


function showBibTeX() {
    uproot.alert(`<h5 class="mb-3">Pre-formatted citation <span class="fw-light">(Chicago style)</span></h5>
<p class="mb-4">Grossmann, Max&nbsp;R.&nbsp;P., and Holger Gerhardt. 2025. “uproot: An Experimental Framework with a Focus on Performance, Flexibility, and Ease of Use.” Unpublished manuscript.</p>
<h5 class="mb-3">BibTeX entry</h5>
<code>
<b>@unpublished</b>{<b>uproot</b>,<br>
&nbsp;&nbsp;<b>author</b> = {Grossmann, Max~R.~P. and Gerhardt, Holger},<br>
&nbsp;&nbsp;<b>title</b>&nbsp;= {uproot: An Experimental Framework with a~Focus on Performance, Flexibility, and Ease of Use},<br>
&nbsp;&nbsp;<b>year</b>&nbsp;= {2025},<br>
&nbsp;&nbsp;<b>note</b>&nbsp;= {Unpublished manuscript}<br>
}
</code>`);
}
