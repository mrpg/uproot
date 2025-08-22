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
        container.innerHTML = "";
    }

    sortedRooms.forEach(room => {
        const card = document.createElement("div");
        card.className = "border-uproot-light card mb-3";

        // Card header with room name and status

        const cardHeader = document.createElement("div");
        cardHeader.className = "align-items-center bg-uproot-light border-uproot-light card-header d-flex justify-content-between py-2 text-uproot";

        const title = document.createElement("h5");
        title.className = "fw-bold font-monospace mb-0 me-3";
        title.textContent = room.name;
        cardHeader.appendChild(title);

        const rightCol = document.createElement("div");
        //rightCol.className = "text-end";
        const statusBadge = document.createElement("span");
        statusBadge.className =
            room.start ? "badge bg-success border border-success fs-6 my-1" : "badge border border-danger fs-6 my-1 text-danger";
        statusBadge.textContent = room.start ? _("Started") : _("Inactive");
        rightCol.appendChild(statusBadge);

        cardHeader.appendChild(rightCol);
        card.appendChild(cardHeader);

        // Card body with config, session info, and links

        const cardBody = document.createElement("div");
        cardBody.className = "bg-light card-body d-flex justify-content-between pb-1 pt-3 rounded-bottom";

        // Left column for config and session info

        const leftCol = document.createElement("div");
        leftCol.className = "col-4";

        const configItem = document.createElement("div");
        configItem.className = "mb-0";
        const configLabel = document.createElement("span");
        configLabel.className = "fw-bold";
        configLabel.textContent = `${_("Config")}: `;
        const configValue = document.createElement("span");
        if (room.config) {
            configValue.textContent = room.config;
            configValue.className = "font-monospace";
        } else {
            configValue.textContent = _("N/A");
            configValue.className = "text-muted";
        }
        configItem.appendChild(configLabel);
        configItem.appendChild(configValue);
        leftCol.appendChild(configItem);

        const sessionItem = document.createElement("div");
        //sessionItem.className = "mb-2";
        const sessionLabel = document.createElement("span");
        sessionLabel.className = "fw-bold";
        sessionLabel.textContent = `${_("Session")}: `;
        const sessionValue = document.createElement("span");
        if (room.sname) {
            sessionValue.className = "font-monospace";
            sessionValue.textContent = room.sname;
        } else {
            sessionValue.textContent = _("N/A");
            sessionValue.className = "text-muted";
        }
        sessionItem.appendChild(sessionLabel);
        sessionItem.appendChild(sessionValue);
        leftCol.appendChild(sessionItem);

        const labelsBadge = document.createElement("div");
        //labelsBadge.className = "mb-2";
        if (room.labels != null && room.labels.length > 0) {
            labelsBadge.innerHTML = `<b>${_("Labels")}:</b> ${room.labels.length}`;
            labelsBadge.title = room.labels.slice(0, 5).join(", ") + (room.labels.length > 5 ? "..." : "");
        } else{
            labelsBadge.innerHTML = `<b>${_("Labels")}:</b> N/A`;
        }
        leftCol.appendChild(labelsBadge);

        const freejoin = room.labels == null && room.capacity == null;
        const freejoinBadge = document.createElement("div");
        freejoinBadge.className = "mb-2";
        if (freejoin) {
            freejoinBadge.innerHTML = `<b>${_("Join mode")}:</b> ${_("free join")}`;
        } else {
            freejoinBadge.innerHTML = `<b>${_("Join mode")}:</b> ${_("restricted")}`;
        }
        leftCol.appendChild(freejoinBadge);

        cardBody.appendChild(leftCol);

        // Middle column for links

        const links = document.createElement("div");
        links.className = "d-flex flex-column justify-content-center";

        if (room.sname) {
            const sessionLink = document.createElement("a");
            sessionLink.href = `${uproot.vars.root}/admin/session/${encodeURIComponent(room.sname)}/`;
            sessionLink.className = "btn btn-sm btn-outline-uproot btn-view-details d-block me-2 py-0";
            sessionLink.innerHTML = "&boxbox;";
            sessionLink.title = _("View session");
            links.appendChild(sessionLink);
        } else {
            const sessionLink = document.createElement("button");
            sessionLink.disabled = true;
            sessionLink.className = "btn btn-sm btn-view-details d-block me-2 py-0 opacity-25";
            sessionLink.innerHTML = "&boxbox;";
            links.appendChild(sessionLink);
        }

        const joinLink = document.createElement("a");
        joinLink.href = `${uproot.vars.root}/admin/room/${encodeURIComponent(room.name)}/`;
        //joinLink.setAttribute("target", "_blank");
        joinLink.className = "btn btn-sm btn-outline-uproot btn-view-details";
        joinLink.innerHTML = "&rarr;";
        joinLink.title = _("View room");
        links.appendChild(joinLink);
        /*const joinLink = document.createElement("a");
        joinLink.href = `${uproot.vars.root}/room/${encodeURIComponent(room.name)}/`;
        joinLink.setAttribute("target", "_blank");
        joinLink.className = "fs-sm fw-bolder link-danger link-offset-2 link-underline-danger link-underline-opacity-0 link-underline-opacity-100-hover";
        joinLink.innerHTML = _("Enter room as a participant");
        joinLink.title = _("Enter room as a participant");
        links.appendChild(joinLink);*/

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
                    n_players < room.capacity ? "badge bg-warning border border-warning fs-6 text-dark" : "badge bg-success border border-success fs-6";
                // If session is less than 90% full, show as danger
                capacityBadge.className =
                    n_players < 0.9 * room.capacity ? "badge bg-danger border border-danger fs-6" : "badge bg-warning border border-warning fs-6";
            } else {
                capacityBadge.className = "badge border border-danger fs-6 ms-2 text-danger"
            }
            capacityBadge.textContent = `${_("Capacity")}: ${room.capacity}`;
        } else {
            if (room.start) {
                capacityBadge.className = "badge bg-success border border-success fs-6";
                capacityBadge.textContent = _("Capacity") + ": " + _("any");
            } else {
                capacityBadge.className = "badge border border-success fs-6 text-success";
                capacityBadge.textContent = _("Capacity") + ": " + _("any");
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
                    n_players < room.capacity ? "badge bg-warning border border-warning fs-6 ms-2 text-dark" : "badge bg-success boder border-success fs-6";
                // If session is less than 90% full, show as danger
                nPlayersBadge.className =
                    n_players < 0.9 * room.capacity ? "badge bg-danger border border-danger fs-6 ms-2" : "badge bg-warning border border-warning fs-6 ms-2";
                nPlayersBadge.textContent = `${_("Players")}: ${n_players}`;
            } else {
                nPlayersBadge.className = "badge bg-success border border-success fs-6 ms-2";
                nPlayersBadge.textContent = `${_("Players")}: ${n_players}`;
            }
        } else {
            nPlayersBadge.className = room.start ? "badge bg-danger border border-danger fs-6 ms-2" : "badge border border-danger fs-6 ms-2 text-danger";
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
        container.appendChild(card);
    });
}

function renderSessions(sessions, containerId) {
    const container = I(containerId);
    const sortedSessions = Object.values(sessions).sort((a, b) => (b.started || 0) - (a.started || 0));

    if (sortedSessions.length > 0) {
        container.innerHTML = "";
    }

    sortedSessions.forEach(session => {
        const card = document.createElement("div");
        card.className = "border-uproot-light card mb-3";

        const cardHeader = document.createElement("div");
        cardHeader.className = "align-items-center bg-uproot-light border-uproot-light card-header d-flex justify-content-between py-1";

        const headerContent = document.createElement("div");

        if (session.sname) {
            const title = document.createElement("h5");
            title.className = "d-inline-block fw-bold font-monospace mb-0 me-5";
            title.textContent = session.sname;
            headerContent.appendChild(title);
        }

        if (session.started) {
            const time = document.createElement("small");
            time.className = "text-muted";
            time.textContent = `${_("Started")}: ` + epochToLocalDateTime(session.started);
            headerContent.appendChild(time);
        }

        cardHeader.appendChild(headerContent);

        if (session.sname) {
            const detailsLink = document.createElement("a");
            detailsLink.href = `${uproot.vars.root}/admin/session/${encodeURIComponent(session.sname)}/`;
            detailsLink.className = "btn btn-sm btn-outline-uproot btn-view-details py-0";
            detailsLink.innerHTML = "&boxbox;";
            detailsLink.title = _("View session details");
            cardHeader.appendChild(detailsLink);
        }

        const cardBody = document.createElement("div");
        cardBody.className = "bg-light card-body d-flex flex-row justify-content-between pb-2 pt-2 rounded-bottom";

        const configItem = document.createElement("div");
        configItem.className = "mt-1";
        const configLabel = document.createElement("span");
        configLabel.className = "fw-bold";
        configLabel.textContent = `${_("Config")}: `;
        const configValue = document.createElement("span");
        if (session.config) {
            configValue.textContent = session.config;
        } else {
            configValue.textContent = _("N/A");
            configValue.className = "text-muted";
        }
        configItem.appendChild(configLabel);
        configItem.appendChild(configValue);
        cardBody.appendChild(configItem);

        if (session.description) {
            const descItem = document.createElement("div");
            descItem.className = "mt-1";
            const descLabel = document.createElement("span");
            descLabel.className = "fw-bold";
            descLabel.textContent = `${_("Description")}: `;
            const descValue = document.createElement("span");
            descValue.textContent = session.description;
            descItem.appendChild(descLabel);
            descItem.appendChild(descValue);
            cardBody.appendChild(descItem);
        }

        const badges = document.createElement("div");
        badges.className = "";

        if (session.n_players != null) {
            const badge = document.createElement("span");
            badge.className = "badge bg-uproot border border-uproot me-2 mb-1 mt-2";
            badge.textContent = session.n_players + " players";
            badges.appendChild(badge);
        }

        if (session.n_groups != null) {
            const badge = document.createElement("span");
            badge.className = "badge bg-white border border-uproot me-2 text-uproot";
            badge.textContent = session.n_groups + " groups";
            badges.appendChild(badge);
        }

        if (session.room) {
            const badge = document.createElement("span");
            badge.className = "badge bg-info";
            badge.textContent = `${_("Room")}: ` + session.room;
            badges.appendChild(badge);
        }

        if (badges.children.length > 0) {
            cardBody.appendChild(badges);
        }

        card.appendChild(cardHeader);
        if (cardBody.children.length > 0) {
            card.appendChild(cardBody);
        }
        container.appendChild(card);
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
    container.innerHTML +=
        "<label for='configs-apps-select'>" + _("Config or app") + "</label>";
}

function renderConfigsAppsCards(data, containerId, groupKey) {
    const container = I(containerId);
    if (!data[groupKey]) return;

    const card = document.createElement("div");
    card.className = "card mb-3";

    const cardBody = document.createElement("div");
    if (groupKey === "configs") {
        cardBody.className = "bg-light card-body px-3 py-1 rounded";
    } else {
        cardBody.className = "card-body px-3 py-1";
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
        title.className = "fw-bold";
        title.textContent = key_;
        content.appendChild(title);

        if (value != null && value !== "") {
            const desc = document.createElement("div");
            //desc.className = "text-muted";
            desc.textContent = value;
            content.appendChild(desc);
        }

        item.appendChild(content);

        const detailsLink = document.createElement("a");
        detailsLink.href = `${uproot.vars.root}/admin/new_session/?config=${encodeURIComponent(key)}`;
        detailsLink.className = "btn btn-sm btn-outline-uproot btn-launch";
        detailsLink.innerHTML = "&neArr;";
        detailsLink.title = _("Start session");
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
