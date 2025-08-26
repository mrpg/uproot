function ppath(pageOrder, showPage) {
    if (Array.isArray(pageOrder)) {
        if (Number.isInteger(showPage) && showPage >= 0 && showPage < pageOrder.length) {
            return pageOrder[showPage];
        }
        if (showPage === -1) return "Initialize.html";
    }
    return "End.html";
}

function replaceChildren(el, ...children) {
    while (el.firstChild) el.removeChild(el.firstChild);
    for (const c of children) el.appendChild(c);
}

function renderPageName(targetCell, path) {
    const container = document.createDocumentFragment();

    const s = path.lastIndexOf("/");
    let dir = "", nameExt = path;
    if (s !== -1) { dir = path.slice(0, s + 1); nameExt = path.slice(s + 1); }

    const d = nameExt.lastIndexOf(".");
    let name = nameExt, ext = "";
    if (d > 0) { name = nameExt.slice(0, d); ext = nameExt.slice(d); }

    if (dir) {
        const spanDir = document.createElement("span");
        spanDir.className = "app";
        spanDir.textContent = dir; // safe
        container.append(spanDir);
    }
    const spanName = document.createElement("span");
    spanName.className = "page";
    spanName.textContent = name; // safe
    container.append(spanName);

    if (ext) {
        const spanExt = document.createElement("span");
        spanExt.className = "extension";
        spanExt.textContent = ext; // safe
        container.append(spanExt);
    }

    replaceChildren(targetCell, container);
}

class PlayerMonitor {
    constructor(tableId = "players") {
        this.tm = new TableManager(tableId, false);

        // Ensure headers exist (match ViewData naming) then remove probe row.
        // TODO: "label"
        // TODO: Link "player" to player page
        ["check", "id", "label", "player", "page", "progress", "lastSeen"].forEach(c =>
            this.tm.getCell("__headerProbe__", c)
        );
        const probe = this.tm.rows.get("__headerProbe__");
        if (probe) { probe.remove(); this.tm.rows.delete("__headerProbe__"); }

        // Event delegation for row clicks (toggle checkbox unless clicking controls)
        const table = I(tableId);
        if (table) {
            table.addEventListener("click", (e) => {
                const tr = e.target.closest("tr");
                if (!tr || e.target.closest("input,button,a,textarea,select,label,[role='button']")) return;
                const cb = tr.querySelector(".player-checkbox");
                if (cb) {
                    cb.checked = !cb.checked; this._syncRowActiveState(cb);
                    I("checkAll").checked = this.allChecked();  // sync "check all" state
                }
            });
        }
    }

    upsertPlayer(uname, { id, pageName, currentStep, totalSteps, pageOrder, lastSeen }) {
        // PLAYER = [checkbox] uname ♥
        const playerCell = this.tm.getCell(uname, "player");
        const checkCell = this.tm.getCell(uname, "check");
        if (!playerCell.dataset.wired) {
            const label = document.createElement("label");
            label.className = "d-inline-flex align-items-center gap-2 m-0";

            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.className = "form-check-input player-checkbox";
            cb.dataset.playerUname = uname;
            cb.addEventListener("change", () => {
                this._syncRowActiveState(cb);
                I("checkAll").checked = this.allChecked();  // uncheck "check all" if any row is manually checked
            });
            checkCell.appendChild(cb);

            const nameSpan = document.createElement("span");
            nameSpan.className = "player-name";

            const heart = document.createElement("span");
            heart.className = "heartbeat";
            heart.setAttribute("aria-hidden", "true");
            heart.textContent = "♥";

            label.append(nameSpan, heart);
            replaceChildren(playerCell, label);
            playerCell.dataset.wired = "1";
        }
        playerCell.querySelector(".player-name").innerHTML = // SAFE
            `<a
                class="link-dark link-offset-2 link-underline-dark link-underline-opacity-25 link-underline-opacity-100-hover"
                href="${uproot.vars.root}/p/${uproot.vars.sname}/${uname}/" target="_blank">${uname}
            </a>`;

        // ID
        this.tm.getCell(uname, "id").textContent = id ?? "";

        // Page (safe)
        renderPageName(this.tm.getCell(uname, "page"), pageName || "");

        // Progress (+ tooltip of full order)
        const pc = this.tm.getCell(uname, "progress");
        let indicator = pc.querySelector(".progress-indicator");
        if (!indicator) {
            indicator = document.createElement("span");
            indicator.className = "progress-indicator";
            indicator.setAttribute("title", "");
            pc.appendChild(indicator);
        }
        const safeCurrent = Math.max(0, Number(currentStep) || 0);
        const safeTotal = Math.max(0, Number(totalSteps) || 0);
        indicator.textContent = `${safeCurrent}/${safeTotal}`;
        this._initProgressTooltip(indicator, Array.isArray(pageOrder) ? pageOrder : []);
        // Last seen
        //this.tm.getCell(uname, "lastSeen").textContent = lastSeen || "";
        const lastSeenHhMmSs =
            `${lastSeen.slice(-8, -3)}<span class='text-secondary opacity-50'>${lastSeen.slice(-3)}</span>`
        const lastSeenCell = this.tm.getCell(uname, "lastSeen");
        lastSeenCell.innerHTML = // SAFE
            `<span class="lastSeen-indicator" title="${lastSeen}">${lastSeenHhMmSs}</span>`;
        let indicatorLastSeen = lastSeenCell.querySelector(".lastSeen-indicator");
        this._initLastSeenTooltip(indicatorLastSeen, lastSeen);
    }

    triggerHeartbeat(uname) {
        const row = this._getRow(uname);
        const heart = row?.querySelector(".heartbeat");
        if (!heart) return;
        heart.classList.remove("active"); // reset if mid-animation
        // Force reflow so the animation can restart
        heart.offsetWidth;
        heart.classList.add("active");
        setTimeout(() => heart.classList.remove("active"), 5000);
    }

    checkAll(checked = true) {
        const table = I("players");
        if (!table) return;
        table.querySelectorAll(".player-checkbox").forEach(cb => {
            cb.checked = !!checked;
            this._syncRowActiveState(cb);
        });
    }

    allChecked() {
        const table = I("players");
        if (!table) return;
        return [...table.querySelectorAll(".player-checkbox")].map(cb => cb.checked).every(Boolean);
    }

    getSelectedPlayers() {
        const table = I("players");
        if (!table) return [];
        return Array.from(table.querySelectorAll(".player-checkbox:checked"))
            .map(cb => cb.dataset.playerUname)
            .filter(Boolean);
    }

    _getRow(uname) { return this.tm.rows.get(uname) || null; }

    _initProgressTooltip(element, pageOrder) {
        const txt = pageOrder.length ? pageOrder.join(" → ") : "";
        try {
            const prev = (window.bootstrap?.Tooltip)?.getInstance(element);
            if (prev) prev.dispose();
            if (txt && window.bootstrap?.Tooltip) {
                new window.bootstrap.Tooltip(element, { title: txt, placement: "top" });
            } else {
                element.setAttribute("title", txt); // fallback
            }
        } catch {
            element.setAttribute("title", txt); // graceful fallback
        }
    }

    _initLastSeenTooltip(element, lastSeen) {
        const txt = lastSeen || "";
        try {
            const prev = (window.bootstrap?.Tooltip)?.getInstance(element);
            if (prev) prev.dispose();
            if (txt && window.bootstrap?.Tooltip) {
                new window.bootstrap.Tooltip(element, { title: txt, placement: "top" });
            } else {
                element.setAttribute("title", txt);  // fallback
            }
        } catch {
            element.setAttribute("title", txt);  // graceful fallback
        }
    }

    _syncRowActiveState(cb) {
        const tr = cb.closest("tr");
        if (!tr) return;
        tr.classList.toggle("active", cb.checked);
    }
}

const monitor = new PlayerMonitor();

function toPlayerPayload(uname, onlineMap, infoTuple) {
    const id = infoTuple?.[0];
    const pageOrder = Array.isArray(infoTuple?.[1]) ? infoTuple[1] : [];
    const showPage = Number.isInteger(infoTuple?.[2]) ? infoTuple[2] : -1;
    const pageName = ppath(pageOrder, showPage);
    const lastSeen = onlineMap?.[uname] == null ? "—" : epochToLocalISO(onlineMap[uname]);

    return {
        id,
        pageName,
        currentStep: showPage + 1,
        totalSteps: pageOrder.length,
        pageOrder,
        lastSeen,
    };
}

/* ===== Public API (kept global for compatibility) ===== */

window.new_info_online = function new_info_online(data) {
    if (!window.uproot) return;
    uproot.vars.online = data.online || {};
    uproot.vars.info = data.info || {};
    for (const [uname, infoTuple] of Object.entries(uproot.vars.info)) {
        monitor.upsertPlayer(uname, toPlayerPayload(uname, uproot.vars.online, infoTuple));
    }
};

window.invoke_from_monitor = function invoke_from_monitor(fname, ...args) {
    return window.uproot?.invoke(
        fname,
        window.uproot?.vars?.sname,
        monitor.getSelectedPlayers(),
        ...args,
    );
};

window.actually_manage = function actually_manage() {
    const action = window.uproot?.selectedValue("manage");
    if (action) {
        window.bootstrap?.Modal.getOrCreateInstance(I("manage-modal")).hide();
        window.invoke_from_monitor(action).then((data) => {
            if (data) window.new_info_online(data);
            window.uproot?.alert("The action has completed.");
        });
    } else {
        window.uproot?.error("No action was selected.");
    }
};

window.actually_insert = function actually_insert() {
    const json = I("json-input")?.value ?? "";
    const reload = !!I("reload2")?.checked;
    let fields;
    try {
        fields = JSON.parse(json);
    } catch {
        return window.uproot?.error("Invalid JSON.");
    }
    window.bootstrap?.Modal.getOrCreateInstance(I("insert-modal")).hide();
    window.invoke_from_monitor("insert_fields", { fields, reload }).then(() => {
        window.uproot?.alert("The action has completed.");
    });
};

window.actually_adminmessage_send = function actually_adminmessage_send() {
    const msg = I("adminmsg")?.value ?? "";
    window.bootstrap?.Modal.getOrCreateInstance(I("adminmessage_send-modal")).hide();
    window.invoke_from_monitor("adminmessage", msg).then(() => {
        window.uproot?.alert("The action has completed.");
    });
};

window.mmodal = function mmodal(moname) {
    const selected = monitor.getSelectedPlayers();
    const modal = window.bootstrap?.Modal.getOrCreateInstance(I(`${moname}-modal`));
    if (selected.length > 0) {
        document.querySelectorAll(".pcount").forEach((el) => { el.innerText = String(selected.length); });
        modal?.show();
    } else {
        window.uproot?.error("No subjects were selected.");
    }
};

window.uproot?.onCustomEvent("Attended", (event) => {
    // TODO: handle event?.detail?.online == null
    const uname = event?.detail?.uname;
    const info = event?.detail?.info;
    if (!uname || !Array.isArray(info)) return;

    const payload = toPlayerPayload(uname, { [uname]: 0 }, info);
    // For "lastSeen" on attendance, always show now:
    now = new Date();
    payload.lastSeen = epochToLocalISO(now.getTime() / 1000);  // convert ms to seconds
    monitor.upsertPlayer(uname, payload);

    monitor.triggerHeartbeat(uname);
});

window.uproot?.onStart(() => {
    const info = window.uproot?.vars?.info || {};
    const online = window.uproot?.vars?.online || {};
    for (const [uname, tuple] of Object.entries(info)) {
        monitor.upsertPlayer(uname, toPlayerPayload(uname, online, tuple));
    }
    window.uproot?.invoke("subscribe_to_attendance", window.uproot?.vars?.sname);
    monitor.tm._applySort("id", "asc");
    document.querySelector("th[data-col-id='check']").innerHTML = // SAFE
        "<input class='form-check-input' id='checkAll' onclick='monitor.checkAll(this.checked)' type='checkbox'>";
    document.querySelector("th[data-col-id='check']").classList.remove("sortable");
});
