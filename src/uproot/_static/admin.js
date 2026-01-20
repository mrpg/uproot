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
        col.className = "col mb-4";
        const card = document.createElement("div");
        card.className = "border-uproot-light card";

        // Card header with room name and status

        const cardHeader = document.createElement("div");
        cardHeader.className = "bg-white border-0 card-header";

        const headerContent = document.createElement("div");
        headerContent.className = "align-items-center border-bottom border-uproot-light d-flex justify-content-between pb-2 pt-1 text-uproot";
        const title = document.createElement("h5");
        title.className = "fw-semibold mb-1 me-3 text-nowrap";
        title.innerHTML =  // SAFE
            `<a class="link-offset-2 link-underline-opacity-0 link-underline-opacity-100-hover link-underline-uproot text-uproot" href="${uproot.vars.root}/admin/room/${encodeURIComponent(room.name)}/"><span class="font-monospace">${encodeURIComponent(room.name)}</span> <i class="font-bi">&#xF891;</i></a>`;  // bi-house-gear
        headerContent.appendChild(title);

        const rightCol = document.createElement("div");
        //rightCol.className = "text-end";
        const statusBadge = document.createElement("div");
        statusBadge.className =
            room.open ? "badge bg-success border border-success my-1" : "badge border border-danger my-1 text-danger";
        statusBadge.textContent = room.open ? _("room is Open") : _("Closed");
        rightCol.appendChild(statusBadge);

        headerContent.appendChild(rightCol);
        cardHeader.appendChild(headerContent);
        card.appendChild(cardHeader);

        // Card body with config, session info, and links

        const cardBody = document.createElement("div");
        cardBody.className = "bg-white card-body d-flex justify-content-between pb-1 pt-1 rounded-bottom";

        // Left column for config and session info

        const leftCol = document.createElement("div");
        leftCol.className = "col d-table mb-2";

        const sessionItem = document.createElement("div");
        sessionItem.className = "d-table-row";
        const sessionLabel = document.createElement("span");
        sessionLabel.className = "d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase";
        sessionLabel.textContent = `${_("Session")} `;
        const sessionValue = document.createElement("span");
        if (room.sname) {
            sessionValue.className = "d-table-cell font-monospace w-100";
            sessionValue.innerHTML =  // SAFE
                `<a class="link-subtle" href="${uproot.vars.root}/admin/session/${encodeURIComponent(room.sname)}/">${encodeURIComponent(room.sname)}</a>`
        } else {
            sessionValue.className = "d-table-cell text-body-tertiary w-100";
            sessionValue.textContent = _("N/A");
        }
        sessionItem.appendChild(sessionLabel);
        sessionItem.appendChild(sessionValue);
        leftCol.appendChild(sessionItem);

        const configItem = document.createElement("div");
        configItem.className = "d-table-row";
        const configLabel = document.createElement("span");
        configLabel.className = "d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase";
        configLabel.textContent = `${_("Config")} `;
        const configValue = document.createElement("span");
        if (room.config) {
            configValue.textContent = room.config;
            configValue.className = "d-table-cell font-monospace w-100";
        } else {
            configValue.textContent = _("N/A");
            configValue.className = "d-table-cell text-body-tertiary w-100";
        }
        configItem.appendChild(configLabel);
        configItem.appendChild(configValue);
        leftCol.appendChild(configItem);

        const labelsItem = document.createElement("div");
        labelsItem.className = "d-table-row";
        if (room.labels != null && room.labels.length > 0) {
            labelsItem.innerHTML =  // SAFE
                `<span class="d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase">${_("Labels")}</span> <span class="d-table-cell w-100">${room.labels.length}</span>`;
            labelsItem.title = room.labels.slice(0, 5).join(", ") + (room.labels.length > 5 ? "..." : "");
        } else{
            labelsItem.innerHTML =  // SAFE
                `<span class="d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase">${_("Labels")}</span> <span class="d-table-cell text-body-tertiary w-100">N/A</span>`;
        }
        leftCol.appendChild(labelsItem);

        const freejoin = room.labels == null && room.capacity == null;
        const freejoinItem = document.createElement("div");
        freejoinItem.className = "d-table-row";
        if (freejoin) {
            freejoinItem.innerHTML =  // SAFE
                `<span class="d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase">${_("Join mode")}</span> <span class="d-table-cell w-100">${_("free join")}</span>`;
        } else {
            freejoinItem.innerHTML =  // SAFE
                `<span class="d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase">${_("Join mode")}</span> <span class="d-table-cell w-100">${_("restricted")}</span>`;
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
        badges.className = "align-items-end d-flex flex-column justify-content-center";

        var n_players = 0
        if (room.sname && uproot.vars.sessions[room.sname]) {
            n_players = uproot.vars.sessions[room.sname].n_players;
        }

        const capacityBadge = document.createElement("div");
        if (room.capacity != null) {
            if (room.open) {
                // If full, show as success; if more than 90% full, show as warning; otherwise show as danger
                capacityBadge.className =
                    n_players < 0.9 * room.capacity ? "badge bg-danger border border-danger mb-2" :
                        (n_players < room.capacity ? "badge bg-warning border border-warning mb-2 text-dark" : "badge bg-success border border-success mb-2");
            } else {
                capacityBadge.className = "badge border border-danger mb-2 text-danger"
            }
            capacityBadge.textContent = `${_("Capacity")}: ${room.capacity}`;
        } else {
            if (room.open) {
                capacityBadge.className = "badge bg-success border border-success mb-2";
                capacityBadge.textContent = _("Capacity") + ": ∞";
            } else {
                capacityBadge.className = "badge border border-success mb-2 text-success";
                capacityBadge.textContent = _("Capacity") + ": ∞";
            }
        }
        badges.appendChild(capacityBadge);

        const nPlayersBadge = document.createElement("div");
        console.log(room.sname);
        if (room.sname && uproot.vars.sessions[room.sname]) {
            if (room.capacity != null) {
                // If full, show as success; if more than 90% full, show as warning; otherwise show as danger
                nPlayersBadge.className =
                    n_players < 0.9 * room.capacity ? "badge bg-danger border border-danger mb-2" :
                        (n_players < room.capacity ? "badge bg-warning border border-warning mb-2 text-dark" : "badge bg-success boder border-success mb-2");
                nPlayersBadge.textContent = `${_("Players")}: ${n_players}`;
            } else {
                nPlayersBadge.className = "badge bg-success border border-success mb-2";
                nPlayersBadge.textContent = `${_("Players")}: ${n_players}`;
            }
        }
        badges.appendChild(nPlayersBadge);

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
        col.className = "col mb-4";
        const card = document.createElement("div");
        card.className = "card";

        const cardHeader = document.createElement("div");
        cardHeader.className = "bg-white border-0 card-header";

        const headerContent = document.createElement("div");
        headerContent.className = "align-items-center border-bottom border-uproot-light d-flex justify-content-between pb-2 pt-1"

        if (session.sname) {
            const title = document.createElement("h5");
            title.className = "d-inline-block fw-semibold mb-1 me-3 text-nowrap";
            title.innerHTML =  // SAFE
                `<a class="link-dark link-offset-2 link-underline-opacity-0 link-underline-opacity-100-hover link-underline-opacity-0" href="${uproot.vars.root}/admin/session/${encodeURIComponent(session.sname)}/"><span class="font-monospace">${encodeURIComponent(session.sname)}</span> <i class="font-bi">&#xF8A7;</i></a>`  // bi-person-gear
            headerContent.appendChild(title);
        }

        if (session.started) {
            const time = document.createElement("small");
            time.className = "badge border border-opacity-0 border-white fw-normal px-0 my-1 text-body-tertiary";
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
        cardBody.className = "bg-white card-body d-flex flex-row justify-content-between pb-2 pt-0 rounded-bottom";

        const configRoomItem = document.createElement("div");
        configRoomItem.className = "d-table mb-2 mt-1";
        const roomItem = document.createElement("div");
        roomItem.className = "d-table-row";
        const roomLabel = document.createElement("span");
        roomLabel.className = "d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase";
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
        configLabel.className = "d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase";
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
        descLabel.className = "d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase";
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
        badges.className = "align-items-end d-flex flex-column justify-content-center";

        /*
        if (session.room) {
            const badge = document.createElement("span");
            badge.className = "badge bg-uproot-light border border-uproot mb-1 me-2 text-uproot";
            badge.textContent = `${_("Room")}: ` + session.room;
            badges.appendChild(badge);
        }
        */

        if (session.n_players != null) {
            const badge = document.createElement("div");
            badge.className = "badge bg-uproot border border-uproot mb-2";
            badge.textContent = `${_("Players")}: ${session.n_players}`;
            badges.appendChild(badge);
        }

        if (session.n_groups != null) {
            const badge = document.createElement("div");
            badge.className = "badge bg-white border border-uproot ms-2 text-uproot";
            badge.textContent = ` ${_("Groups")}: ${session.n_groups}`;
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
    const label = document.createElement("label");

    select.className = "form-select";
    select.id = "configs-apps-select";
    select.name = "config";

    select.addEventListener("change", (e) => {
        const value = e.target.value;

        if (typeof configSelected !== "undefined") {
            configSelected(value);
        }
    });

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

    label.htmlFor = "configs-apps-select";
    label.textContent = _("Config or app");
    container.appendChild(label);

    return select;
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
        item.className = "align-items-center bg-transparent d-flex justify-content-between list-group-item p-0";

        const content = document.createElement("div");
        const key_ = key.startsWith("~") ? key.substr(1) : key;

        const title = document.createElement("div");
        title.className = "font-monospace fw-semibold h5 my-2";
        title.textContent = key_;
        content.appendChild(title);

        if (value != null && value !== "") {
            const desc = document.createElement("div");
            desc.className = "d-table mb-2"
            const descLabel = document.createElement("div");
            descLabel.className = "d-table-cell fs-sm fw-medium opacity-75 pe-4 text-ls-uppercase text-nowrap text-uppercase";
            descLabel.textContent = key.startsWith("~") ? _("Description") : _("Apps");
            const descContent = document.createElement("div");
            descContent.className =
                key.startsWith("~") ? "d-table-cell w-100" : "d-table-cell font-monospace w-100";
            descContent.textContent = value;
            desc.appendChild(descLabel);
            desc.appendChild(descContent);
            content.appendChild(desc);
        }

        item.appendChild(content);

        const detailsLink = document.createElement("a");
        detailsLink.href = `${uproot.vars.root}/admin/sessions/new/?config=${encodeURIComponent(key)}`;
        detailsLink.className = "btn btn-sm btn-outline-uproot btn-launch";
        detailsLink.innerHTML = `<span class="font-bi fs-3">&#xF4FA;</span>`;  // bi-plus-circle  // SAFE
        detailsLink.title = _("New session");
        item.appendChild(detailsLink);

        listGroup.appendChild(item);
    });

    cardBody.appendChild(listGroup);
    card.appendChild(cardBody);
    container.appendChild(card);
}


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
