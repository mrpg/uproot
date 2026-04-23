const adminchatState = {
    overview: {},
    threads: {},
    selectedUnames: new Set(),
    focusedUname: null,
    sending: false,
    filter: "",
    unreadUnames: new Set(),
    syncingSelection: false,
};

function adminchatPlayerUrl(uname) {
    return `${uproot.vars.root}/p/${uproot.vars.sname}/${encodeURIComponent(uname)}/`;
}

function adminchatPageLabel(player) {
    if (typeof player?.page === "string" && player.page !== "") {
        return player.page;
    }

    const showPage = player?.show_page ?? -1;
    const pageOrder = Array.isArray(player?.page_order) ? player.page_order : [];

    if (showPage === -1) {
        return "Initialize.html";
    }

    if (showPage >= 0 && showPage < pageOrder.length) {
        return pageOrder[showPage];
    }

    return "End.html";
}

function adminchatMergeThread(uname, payload) {
    const existing = adminchatState.threads[uname] ?? { messages: [] };
    const currentIds = new Set(existing.messages.map(msg => msg.id));
    const incomingMessages = Array.isArray(payload.messages) ? payload.messages : existing.messages;
    const mergedMessages = [];

    incomingMessages.forEach(msg => {
        if (!currentIds.has(msg.id) || payload.messages) {
            currentIds.add(msg.id);
            mergedMessages.push(msg);
        }
    });

    adminchatState.threads[uname] = {
        ...existing,
        ...payload,
        messages: payload.messages ? payload.messages : [...existing.messages, ...mergedMessages],
    };

    if (payload.chat) {
        adminchatState.overview[uname] = {
            ...(adminchatState.overview[uname] ?? {}),
            ...payload.chat,
        };
    }
}

function adminchatIsUnread(uname) {
    return adminchatState.unreadUnames.has(uname);
}

function adminchatMarkUnread(uname) {
    adminchatState.unreadUnames.add(uname);
}

function adminchatMarkRead(uname) {
    adminchatState.unreadUnames.delete(uname);
}

function adminchatStatusIcon(summary, uname) {
    const unread = adminchatIsUnread(uname);

    if (unread) {
        return `<span class="adminchat-status-dot adminchat-status-unread"></span>`;
    }

    if (!summary) {
        return `<span class="adminchat-status-dot adminchat-status-empty"></span>`;
    }

    if (summary.has_messages && summary.last_sender === "player") {
        return `<span class="adminchat-status-dot adminchat-status-reply"></span>`;
    }

    if (summary.has_messages) {
        return `<span class="adminchat-status-dot adminchat-status-sent"></span>`;
    }

    if (summary.enabled) {
        return `<span class="adminchat-status-dot adminchat-status-open"></span>`;
    }

    return `<span class="adminchat-status-dot adminchat-status-empty"></span>`;
}

function adminchatReplyBadge(summary) {
    if (!summary) {
        return "";
    }

    if (summary.enabled) {
        return `<span class="badge badge-xs text-bg-success">${_("replies on")}</span>`;
    }

    if (summary.has_messages) {
        return `<span class="badge badge-xs text-bg-secondary">${_("read-only")}</span>`;
    }

    return "";
}

function adminchatSnippet(summary, uname) {
    if (!summary?.last_message_text) {
        return `<span class="text-body-tertiary">${_("No messages yet")}</span>`;
    }

    const prefix = summary.last_sender === "admin" ? `${_("You")}: ` : "";
    const text = uproot.escape(summary.last_message_text);
    const unread = adminchatIsUnread(uname);

    if (unread) {
        return `<span class="fw-semibold text-body">${prefix}${text}</span>`;
    }

    return `<span class="text-body-secondary">${prefix}${text}</span>`;
}

function adminchatBulkRepliesState(unames) {
    const enabledCount = unames.reduce((count, uname) => {
        return count + (adminchatState.overview[uname]?.enabled ? 1 : 0);
    }, 0);

    return {
        checked: enabledCount > 0,
        indeterminate: enabledCount > 0 && enabledCount < unames.length,
    };
}

function renderInboxSidebar() {
    const list = I("adminchat-player-list");

    if (!list) {
        return;
    }

    const info = uproot.vars.info || {};
    const unames = Object.keys(info).sort((a, b) => {
        const ua = adminchatIsUnread(a) ? 1 : 0;
        const ub = adminchatIsUnread(b) ? 1 : 0;

        if (ub !== ua) {
            return ub - ua;
        }

        const sa = adminchatState.overview[a];
        const sb = adminchatState.overview[b];
        const ta = sa?.last_message_at ?? 0;
        const tb = sb?.last_message_at ?? 0;

        if (tb !== ta) {
            return tb - ta;
        }

        return a.localeCompare(b);
    });

    const filter = adminchatState.filter.toLowerCase();

    const html = unames.map(uname => {
        if (filter && !uname.toLowerCase().includes(filter)) {
            return "";
        }

        const summary = adminchatState.overview[uname];
        const isSelected = adminchatState.selectedUnames.has(uname);
        const isFocused = adminchatState.focusedUname === uname;
        const unread = adminchatIsUnread(uname);
        const activeClass = isFocused ? "adminchat-inbox-item-active" : "";
        const unreadClass = unread ? "adminchat-inbox-item-unread" : "";
        const count = summary?.message_count ?? 0;
        const nameClass = unread ? "adminchat-inbox-item-name fw-bold" : "adminchat-inbox-item-name";

        return /* SAFE */ `
            <li class="adminchat-inbox-item ${activeClass} ${unreadClass}" data-uname="${uproot.escape(uname)}">
                <div class="adminchat-inbox-item-check">
                    <input type="checkbox" class="form-check-input"
                           data-adminchat-select="1"
                           data-uname="${uproot.escape(uname)}"
                           ${isSelected ? "checked" : ""}
                           aria-label="${_("Select")} ${uproot.escape(uname)}">
                </div>
                <div class="adminchat-inbox-item-body"
                     data-adminchat-focus="1"
                     data-uname="${uproot.escape(uname)}">
                    <div class="adminchat-inbox-item-header">
                        ${adminchatStatusIcon(summary, uname)}
                        <span class="${nameClass}">${uproot.escape(uname)}</span>
                        ${unread ? `<span class="badge badge-xs bg-warning text-dark">${_("new")}</span>` : ""}
                        ${adminchatReplyBadge(summary)}
                    </div>
                    <div class="adminchat-inbox-item-snippet">${adminchatSnippet(summary, uname)}</div>
                    <div class="adminchat-inbox-item-meta">
                        ${count > 0 ? `<span>${count} msg${count !== 1 ? "s" : ""}</span>` : ""}
                    </div>
                </div>
            </li>
        `;
    }).join("");

    list.innerHTML = html || `<li class="adminchat-inbox-empty">${_("No players found")}</li>`;

    list.querySelectorAll("[data-adminchat-select]").forEach((input) => {
        input.addEventListener("click", (event) => {
            event.stopPropagation();
        });

        input.addEventListener("change", (event) => {
            const target = event.currentTarget;
            adminchat.toggleSelect(target.dataset.uname, target.checked);
        });
    });

    list.querySelectorAll("[data-adminchat-focus]").forEach((el) => {
        el.addEventListener("click", (event) => {
            const target = event.currentTarget;
            adminchat.focus(target.dataset.uname);
        });
    });
}

function renderAdminchatMessages(thread) {
    if (!thread.messages || thread.messages.length === 0) {
        return /* SAFE */ `
            <div class="adminchat-empty-state">
                <div class="adminchat-empty-title">${_("No messages yet")}</div>
                <p class="mb-0">${_("Send the first message to open this channel.")}</p>
            </div>
        `;
    }

    return /* SAFE */ `<div class="adminchat-transcript" id="adminchat-transcript">` +
        thread.messages.map((msg) => {
            const isAdmin = msg.sender?.[0] === "admin";
            const sender = isAdmin ? _("Research Coordinator") : uproot.escape(msg.sender?.[1] ?? "");
            const time = msg.time ? epochToLocalISO(msg.time) : "";
            const bubbleClass = isAdmin ? "adminchat-bubble-admin" : "adminchat-bubble-player";

            return /* SAFE */ `
                <article class="adminchat-message ${bubbleClass}">
                    <header class="align-items-center d-flex justify-content-between gap-3 mb-2">
                        <span class="adminchat-message-sender">${sender}</span>
                        <time class="adminchat-message-time">${uproot.escape(time)}</time>
                    </header>
                    <div class="adminchat-message-body">${uproot.escape(msg.text)}</div>
                </article>
            `;
        }).join("") + `</div>`;
}

function renderComposer(opts) {
    const targetLabel = opts.targetLabel;
    const placeholder = opts.placeholder;
    const sendHandler = opts.sendHandler;
    const toggleHandler = opts.toggleHandler ?? null;
    const repliesChecked = opts.repliesChecked ?? false;
    const repliesIndeterminate = opts.repliesIndeterminate ?? false;

    return /* SAFE */ `
        <div class="adminchat-composer-shell">
            <label class="form-label adminchat-meta-label" for="adminchat-message-input">${_("Message")}</label>
            <textarea
                class="form-control adminchat-message-input"
                id="adminchat-message-input"
                rows="4"
                placeholder="${placeholder}"
            ></textarea>
            <div class="align-items-center d-flex flex-wrap justify-content-between gap-3 mt-3">
                <div>
                    ${toggleHandler ? `
                        <div class="form-check form-switch">
                            <input class="form-check-input" type="checkbox" role="switch" id="adminchat-replies-toggle"
                                   data-indeterminate="${repliesIndeterminate ? "1" : "0"}"
                                   ${repliesChecked ? "checked" : ""}
                                   onchange="${toggleHandler}">
                            <label class="form-check-label" for="adminchat-replies-toggle">${_("Player can reply")}</label>
                        </div>
                    ` : ""}
                    <p class="adminchat-helper mb-0 mt-1">${_("Press Enter to send. Use Shift+Enter for a new line.")}</p>
                </div>
                <button
                    class="btn btn-uproot"
                    type="button"
                    ${adminchatState.sending ? "disabled" : ""}
                    onclick="${sendHandler}">
                    ${_("Send")}
                </button>
            </div>
        </div>
    `;
}

function renderSinglePlayerView(uname) {
    const thread = adminchatState.threads[uname];

    if (!thread) {
        return /* SAFE */ `
            <div class="adminchat-empty-state">
                <div class="spinner-border spinner-border-sm text-uproot mb-3" role="status"></div>
                <div class="adminchat-empty-title">${_("Loading conversation...")}</div>
            </div>
        `;
    }

    const player = thread.player;
    const chatInfo = thread.chat;
    const label = player?.label ? uproot.escape(player.label) : `<span class="text-body-tertiary">${_("No label")}</span>`;
    const playerId = player?.id != null ? uproot.escape(String(player.id)) : `<span class="text-body-tertiary">&mdash;</span>`;

    const headerHtml = /* SAFE */ `
        <div class="adminchat-thread-header">
            <div class="d-flex align-items-start justify-content-between gap-3">
                <div>
                    <h4 class="adminchat-player-name mb-1">${uproot.escape(uname)}</h4>
                    <div class="d-flex flex-wrap gap-2 align-items-center">
                        <span class="text-body-secondary">${_("Player ID")}: ${playerId}</span>
                        <span class="text-body-secondary">${_("Label")}: ${label}</span>
                        <span class="text-body-secondary font-monospace">${uproot.escape(adminchatPageLabel(player))}</span>
                    </div>
                </div>
                <a class="btn btn-outline-uproot btn-sm text-nowrap" href="${adminchatPlayerUrl(uname)}" target="_blank">
                    ${_("Open player page")}
                </a>
            </div>
        </div>
    `;

    const messagesHtml = renderAdminchatMessages(thread);

    const composerHtml = renderComposer({
        targetLabel: uproot.escape(uname),
        placeholder: _("Type a message for this participant"),
        sendHandler: "adminchat.sendSingle()",
        toggleHandler: `adminchat.toggleReplies('${uproot.escape(uname)}', this.checked)`,
        repliesChecked: chatInfo?.enabled ?? false,
    });

    return headerHtml + messagesHtml + composerHtml;
}

function renderBroadcastView(unames) {
    const repliesState = adminchatBulkRepliesState(unames);
    const pills = unames.map(u =>
        `<span class="badge bg-uproot-subtle border border-uproot text-uproot">${uproot.escape(u)}</span>`
    ).join(" ");

    return /* SAFE */ `
        <div class="adminchat-broadcast">
            <div class="adminchat-broadcast-header">
                <div class="adminchat-eyebrow mb-2">${_("Broadcast message")}</div>
                <h4 class="fw-semibold mb-2">
                    ${_("Send to #n# players").replace("#n#", unames.length)}
                </h4>
                <div class="adminchat-broadcast-pills mb-3">${pills}</div>
            </div>
            ${renderComposer({
                targetLabel: `${unames.length} ${_("players")}`,
                placeholder: _("Type a message that will be sent to all selected players"),
                sendHandler: "adminchat.sendBroadcast()",
                toggleHandler: "adminchat.bulkEnableReplies(this.checked)",
                repliesChecked: repliesState.checked,
                repliesIndeterminate: repliesState.indeterminate,
            })}
        </div>
    `;
}

function renderMainArea() {
    const main = I("adminchat-main");

    if (!main) {
        return;
    }

    const selected = Array.from(adminchatState.selectedUnames);
    const focused = adminchatState.focusedUname;

    if (focused && selected.length <= 1) {
        main.innerHTML = renderSinglePlayerView(focused);
        scrollTranscript();
        applyReplyToggleState();
        bindComposerKeydown();
        return;
    }

    if (selected.length > 1) {
        main.innerHTML = renderBroadcastView(selected);
        applyReplyToggleState();
        bindComposerKeydown();
        return;
    }

    main.innerHTML = /* SAFE */ `
        <div class="adminchat-empty-state">
            <div class="adminchat-empty-title">${_("Select a player")}</div>
            <p class="mb-0">${_("Click a player in the sidebar, or check multiple to broadcast.")}</p>
        </div>
    `;
}

function scrollTranscript() {
    const transcript = I("adminchat-transcript");

    if (transcript) {
        transcript.scrollTop = transcript.scrollHeight;
    }
}

function bindComposerKeydown() {
    const input = I("adminchat-message-input");

    if (input && input.dataset.uprootBound !== "1") {
        input.dataset.uprootBound = "1";
        input.addEventListener("keydown", (event) => {
            if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();

                if (adminchatState.selectedUnames.size > 1) {
                    adminchat.sendBroadcast();
                } else {
                    adminchat.sendSingle();
                }
            }
        });
    }
}

function applyReplyToggleState() {
    const toggle = I("adminchat-replies-toggle");

    if (toggle) {
        toggle.indeterminate = toggle.dataset.indeterminate === "1";
    }
}

function renderAll() {
    renderInboxSidebar();
    renderMainArea();
}

// ============================================================================
// Selection sync between monitor table and inbox
// ============================================================================

function syncToMonitor() {
    if (!monitorState?.table?.initialized) {
        return;
    }

    adminchatState.syncingSelection = true;

    try {
        const desired = adminchatState.selectedUnames;
        const rows = monitorState.table.getRows();

        rows.forEach(row => {
            const uname = row.getData()?.player;
            const shouldSelect = desired.has(uname);
            const isSelected = row.isSelected();

            if (shouldSelect && !isSelected) {
                row.select();
            } else if (!shouldSelect && isSelected) {
                row.deselect();
            }
        });
    } finally {
        adminchatState.syncingSelection = false;
    }
}

function applyMonitorSelection() {
    if (adminchatState.syncingSelection) {
        return;
    }

    const monitorSelected = typeof getSelectedPlayers === "function" ? getSelectedPlayers() : [];
    const monitorSet = new Set(monitorSelected);

    if (setsEqual(adminchatState.selectedUnames, monitorSet)) {
        return;
    }

    adminchatState.selectedUnames = monitorSet;

    if (monitorSelected.length === 1) {
        adminchatState.focusedUname = monitorSelected[0];
        adminchat.loadThread(monitorSelected[0]);
    } else {
        adminchatState.focusedUname = null;
    }

    renderAll();
}

function setsEqual(a, b) {
    if (a.size !== b.size) {
        return false;
    }

    for (const v of a) {
        if (!b.has(v)) {
            return false;
        }
    }

    return true;
}

// ============================================================================
// Public API
// ============================================================================

window.adminchat = {
    focus(uname) {
        adminchatState.focusedUname = uname;
        adminchatMarkRead(uname);

        if (!adminchatState.selectedUnames.has(uname)) {
            adminchatState.selectedUnames.clear();
            adminchatState.selectedUnames.add(uname);
        } else if (adminchatState.selectedUnames.size > 1) {
            adminchatState.selectedUnames.clear();
            adminchatState.selectedUnames.add(uname);
        }

        this.loadThread(uname);
        renderAll();
        syncToMonitor();
    },

    toggleSelect(uname, checked) {
        if (checked) {
            adminchatState.selectedUnames.add(uname);
        } else {
            adminchatState.selectedUnames.delete(uname);
        }

        if (adminchatState.selectedUnames.size === 1) {
            const only = adminchatState.selectedUnames.values().next().value;
            adminchatState.focusedUname = only;
            adminchatMarkRead(only);
            this.loadThread(only);
        } else if (adminchatState.selectedUnames.size === 0) {
            adminchatState.focusedUname = null;
        } else {
            adminchatState.focusedUname = null;
        }

        renderAll();
        syncToMonitor();
    },

    selectAll() {
        const info = uproot.vars.info || {};
        const filter = adminchatState.filter.toLowerCase();

        Object.keys(info).forEach(uname => {
            if (!filter || uname.toLowerCase().includes(filter)) {
                adminchatState.selectedUnames.add(uname);
            }
        });

        adminchatState.focusedUname = null;
        renderAll();
        syncToMonitor();
    },

    selectNone() {
        adminchatState.selectedUnames.clear();
        adminchatState.focusedUname = null;
        renderAll();
        syncToMonitor();
    },

    selectWithMessages() {
        adminchatState.selectedUnames.clear();

        for (const [uname, summary] of Object.entries(adminchatState.overview)) {
            if (summary?.has_messages) {
                adminchatState.selectedUnames.add(uname);
            }
        }

        if (adminchatState.selectedUnames.size === 1) {
            const only = adminchatState.selectedUnames.values().next().value;
            adminchatState.focusedUname = only;
            adminchatMarkRead(only);
            this.loadThread(only);
        } else {
            adminchatState.focusedUname = null;
        }

        renderAll();
        syncToMonitor();
    },

    async loadThread(uname, force = false) {
        if (!uname) {
            return;
        }

        if (!force && adminchatState.threads[uname]) {
            renderAll();
            return;
        }

        renderAll();

        const payload = await uproot.invoke("adminchat_thread", uproot.vars.sname, uname);
        adminchatMergeThread(uname, payload);
        renderAll();
    },

    async sendSingle() {
        const uname = adminchatState.focusedUname;
        const input = I("adminchat-message-input");

        if (!uname || !input) {
            return;
        }

        const message = input.value.trim();

        if (!message) {
            return;
        }

        adminchatState.sending = true;
        renderAll();

        try {
            const payload = await uproot.invoke(
                "send_adminchat",
                uproot.vars.sname,
                uname,
                message,
            );

            adminchatMergeThread(uname, payload);
        } finally {
            adminchatState.sending = false;
        }

        renderAll();
    },

    async sendBroadcast() {
        const input = I("adminchat-message-input");
        const unames = Array.from(adminchatState.selectedUnames);

        if (!input || unames.length === 0) {
            return;
        }

        const message = input.value.trim();

        if (!message) {
            return;
        }

        adminchatState.sending = true;
        renderAll();

        try {
            const result = await uproot.invoke(
                "send_adminchat_to_players",
                uproot.vars.sname,
                unames,
                message,
            );

            if (result?.players) {
                result.players.forEach(payload => {
                    adminchatMergeThread(payload.player.uname, payload);
                });
            }

            uproot.alert(
                _("Message sent to #n# player(s).").replace("#n#", result?.sent_count ?? unames.length)
            );
        } finally {
            adminchatState.sending = false;
        }

        renderAll();
    },

    async toggleReplies(uname, enabled) {
        const payload = await uproot.invoke(
            "set_adminchat_replies",
            uproot.vars.sname,
            uname,
            enabled,
        );

        adminchatMergeThread(uname, payload);
        renderAll();
    },

    async bulkEnableReplies(enabled) {
        const unames = Array.from(adminchatState.selectedUnames);

        if (unames.length === 0) {
            return;
        }

        const result = await uproot.invoke(
            "set_adminchat_replies_for_players",
            uproot.vars.sname,
            unames,
            enabled,
        );

        if (result?.players) {
            result.players.forEach(payload => {
                const uname = payload.player?.uname;

                if (uname) {
                    adminchatMergeThread(uname, payload);
                }
            });
        }

        const n = result?.players?.length ?? 0;
        const msg = enabled
            ? _("Enabled admin chat replies for #n# player(s).")
            : _("Disabled admin chat replies for #n# player(s).");

        uproot.alert(msg.replace("#n#", n));
        renderAll();
    },

    refreshCurrent() {
        if (adminchatState.focusedUname) {
            this.loadThread(adminchatState.focusedUname, true);
        }
    },
};

// ============================================================================
// Initialization & Events
// ============================================================================

uproot.onStart(() => {
    uproot.invoke("adminchat_overview", uproot.vars.sname).then((data) => {
        adminchatState.overview = data || {};

        for (const [uname, summary] of Object.entries(data || {})) {
            if (summary?.last_sender === "player") {
                adminchatMarkUnread(uname);
            }
        }

        renderAll();
    });

    uproot.invoke("subscribe_to_adminchat", uproot.vars.sname);

    const search = I("adminchat-search");

    if (search) {
        search.addEventListener("input", () => {
            adminchatState.filter = search.value;
            renderInboxSidebar();
        });
    }

    renderAll();
});

window.addEventListener("UprootCustomMonitorSelectionChanged", () => {
    applyMonitorSelection();
});

uproot.onCustomEvent("AdminchatUpdated", (event) => {
    const detail = event.detail || {};
    const uname = detail.uname;

    if (!uname) {
        return;
    }

    const isPlayerMessage = detail.chat?.last_sender === "player"
        || (detail.message && detail.message.sender?.[0] !== "admin");

    if (isPlayerMessage && adminchatState.focusedUname !== uname) {
        adminchatMarkUnread(uname);
    }

    adminchatMergeThread(uname, {
        player: detail.player,
        chat: detail.chat,
        messages: detail.message ? [
            ...(adminchatState.threads[uname]?.messages ?? []).filter(msg => msg.id !== detail.message.id),
            detail.message,
        ] : undefined,
    });

    renderAll();
});
