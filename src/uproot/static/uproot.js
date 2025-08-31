class RobustWebSocket {
    constructor(url, options = {}) {
        this.url = url;
        this.options = options;
        this.ws = null;
        this.messageQueue = [];
        this.reconnectInterval = options.reconnectInterval || 1000;
        this.isConnected = false;
        this.shouldReconnect = true;

        this.connect();
    }

    connect() {
        try {
            this.ws = new WebSocket(this.url);

            this.ws.onopen = () => {
                this.isConnected = true;
                this.processQueue();
                this.options.onOpen?.(this);
            };

            this.ws.onmessage = (event) => {
                this.options.onMessage?.(event, this);
            };

            this.ws.onclose = (event) => {
                this.isConnected = false;
                this.options.onClose?.(event, this);
                if (this.shouldReconnect) {
                    this.scheduleReconnect();
                }
            };

            this.ws.onerror = (error) => {
                this.isConnected = false;
                this.options.onError?.(error, this);
            };

        } catch (error) {
            this.scheduleReconnect();
        }
    }

    scheduleReconnect() {
        setTimeout(() => {
            this.connect();
        }, this.reconnectInterval);
    }

    async send(message) {
        const queueItem = {
            message: message,
            timestamp: Date.now()
        };

        this.messageQueue.push(queueItem);

        if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
            this.processQueue();
        }

        return queueItem;
    }

    processQueue() {
        if (!this.isConnected || this.ws.readyState !== WebSocket.OPEN) {
            return;
        }

        while (this.messageQueue.length > 0) {
            const item = this.messageQueue.shift();

            try {
                this.ws.send(item.message);
                this.options.onMessageSent?.(item, this);
            } catch (error) {
                this.messageQueue.unshift(item);
                this.options.onSendError?.(error, item, this);
                break;
            }
        }
    }


    close() {
        this.shouldReconnect = false;
        this.ws?.close();
    }

    getQueueLength() {
        return this.messageQueue.length;
    }

    clearQueue() {
        this.messageQueue = [];
    }
}

window.uproot = {
    ws: null,
    root: null,
    sname: null,
    uname: null,
    key: null,
    serverThere: null,
    form: null,
    dirty: false,
    futStore: {},
    vars: {},
    receive: null,
    terms: {},
    testing: false,
    timeoutUntil: null,
    timeout1: null,
    timeout2: null,
    verbose: false,
    I: (id_) => document.getElementById(id_),

    aer1945() {
        document.location = "https://www.econlib.org/library/Essays/hykKnw.html";
    },

    setPageTimeout(remainingSeconds) {
        this.timeoutUntil = Date.now() + 1000 * remainingSeconds;

        if (this.timeout1 !== null) {
            window.clearTimeout(this.timeout1);
            window.clearInterval(this.timeout2);
        }

        if (remainingSeconds > 0) {
            this.timeout1 = window.setTimeout(this.submit, 1000 * remainingSeconds);
            this.timeout2 = window.setInterval(this.reshowTimeout, 1000);

            this.reshowTimeout();

            window.dispatchEvent(new CustomEvent(`UprootInternalPageTimeoutSet`));
        }
        else {
            this.submit();
        }
    },

    reshowTimeout() {
        const remainingSeconds = Math.max(0, (uproot.timeoutUntil - Date.now()) / 1000);
        const minutes = Math.floor(remainingSeconds / 60).toString().padStart(2, "0");
        const seconds = Math.floor(remainingSeconds - 60 * minutes).toString().padStart(2, "0");

        I("uproot-time-remaining").innerText = `${minutes}:${seconds}`;
        I("uproot-timeout").style.display = "block";

        if (remainingSeconds < 60) {
            I("uproot-timeout").classList.remove("alert-light");
            I("uproot-timeout").classList.remove("alert-warning");

            if (remainingSeconds < 15) {
                I("uproot-timeout").classList.add("alert-danger");
            }
            else {
                I("uproot-timeout").classList.add("alert-warning");
            }
        }
    },

    getParam(name) {
        return new URLSearchParams(location.search).get(name);
    },

    api(endpoint, data = null) {
        return new Promise((resolve, reject) => {
            const futid = this.uuid();
            this.futStore[futid] = { resolve, reject };

            const message = JSON.stringify({
                endpoint: endpoint,
                payload: data,
                future: futid,
            });

            this.ws.send(message);
        });
    },

    invoke(mname, ...params) {
        const lastParam = params[params.length - 1];
        const isKwargs = params.length > 0 &&
            lastParam != null &&
            typeof lastParam === "object" &&
            !Array.isArray(lastParam);

        const args = isKwargs ? params.slice(0, -1) : params;
        const kwargs = isKwargs ? lastParam : {};

        return uproot.api("invoke", { "mname": mname, "args": args, "kwargs": kwargs });
    },

    queueDispatch(u, entry) {
        if (entry.event !== undefined) {
            if (entry.event.startsWith("_uproot")) {
                const eventName = entry.event.substring(8);
                const ev = new CustomEvent(`UprootInternal${eventName}`, {
                    detail: entry,
                });

                window.dispatchEvent(ev);
            }
            else {
                const eventName = entry.event;
                const ev = new CustomEvent(`UprootCustom${eventName}`, {
                    detail: entry,
                });

                window.dispatchEvent(ev);
            }
        }
        else {
            const ev = new CustomEvent(`UprootQueue`, {
                detail: entry,
            });

            window.dispatchEvent(ev);
        }
    },

    fromServer(event, ws) {
        const msg = Object.assign({ received: Date.now() }, JSON.parse(event.data));
        const kind = msg.kind, payload = msg.payload;

        if (kind === undefined || payload === undefined) {
            /* all server msgs need to have a kind and a payload */
            return;
        }

        if (this.verbose) {
            console.log(msg);
        }

        this.serverThere = Date.now();

        if (kind == "invoke" && "future" in payload) {
            const fut = this.futStore[payload.future];

            if (!payload.error) {
                fut.resolve(payload.data);
            }
            else {
                fut.reject(new Error("Server-side Exception occurred"));
            }

            delete this.futStore[payload.future];
        }
        else if (kind == "action" && "action" in payload) {
            const action = payload.action;

            if (action == "reload") {
                this.reload();
            }
            else if (action == "submit") {
                this.submit();
            }
        }
        else if (kind == "event" && "event" in payload) {
            const eventName = payload.event;
            const ev = new CustomEvent(`UprootCustom${eventName}`, {
                detail: payload.detail,
            });

            window.dispatchEvent(ev);
        }
        else if (kind == "queue") {
            this.queueDispatch(payload.u, payload.entry);
        }
    },

    isPythonIdentifier(str) {
        if (typeof str !== "string" || str.length === 0) return false;
        const re = /^(?:_|[\p{XID_Start}])[\p{XID_Continue}]*$/u;
        return re.test(str);
    },

    hello() {
        return window.uproot.api("hello");
    },

    wsurl() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const host = window.location.host;

        return `${protocol}//${host}${this.root}/ws/${this.sname}/${this.uname}/`;
    },

    wsstart() {
        this.ws = new RobustWebSocket(this.wsurl(), {
            onOpen: (ws) => {
                window.setInterval(this.hello, 9000);

                this.hello().then(() => {
                    window.dispatchEvent(new Event("UprootReady"));
                });
            },
            onMessage: (event, ws) => {
                this.fromServer(event, ws);
            },
        });
    },

    async sha256(text) {
        const encoder = new TextEncoder();
        const data = encoder.encode(text);
        const hash = await crypto.subtle.digest("SHA-256", data);
        return Array.from(new Uint8Array(hash))
            .map(b => b.toString(16).padStart(2, "0"))
            .join("");
    },

    async csrf() {
        const base = `${this.sname}+${this.uname}+${this.key}`;
        return await this.sha256(base);
    },

    init() {
        this.sname = uproot.vars._uproot_internal.sname;
        this.uname = uproot.vars._uproot_internal.uname;
        this.root = uproot.vars._uproot_internal.root;
        this.key = uproot.vars._uproot_internal.key;
        this.form = document.forms[0];

        this.I("_uproot_from").value = uproot.vars._uproot_internal.thisis;

        this.csrf().then((csrf_) => {
            this.I("_uproot_csrf").value = csrf_;
        });
    },

    testingButton(btn) {
        if (this.testing) {
            document.querySelectorAll(".uproot-testing-only").forEach((el) => {
                el.style.display = "none";
            });
            btn.innerText = _("Show testing elements");
        }
        else {
            document.querySelectorAll(".uproot-testing-only").forEach((el) => {
                el.style.display = "block";
            });
            btn.innerText = _("Hide testing elements");
        }

        this.testing = !this.testing;
    },

    uuid() {
        return crypto.randomUUID();
    },

    reload() {
        // this "works" even with POST - skips confirmation
        document.location = document.location;
    },

    submit() {
        return I("uproot-form").submit();
    },

    onStart(fun) {
        window.addEventListener("DOMContentLoaded", fun);
    },

    onReady(fun) {
        window.addEventListener("UprootReady", fun);
    },

    onCustomEvent(evname, fun) {
        window.addEventListener(`UprootCustom${evname}`, fun);
    },

    onInternalEvent(evname, fun) {
        window.addEventListener(`UprootInternal${evname}`, fun);
    },

    onQueue(fun) {
        window.addEventListener(`UprootQueue`, fun);
    },

    selectedValue(name) {
        const radio = document.querySelector(`input[name="${name}"]:checked`);
        if (radio) return radio.value;

        const select = document.querySelector(`select[name="${name}"]`);
        if (select) return select.value;

        return null;
    },

    error(html) {
        const shownModals = Array.from(document.querySelectorAll(".modal.show")).map(el => {
            const modal = bootstrap.Modal.getOrCreateInstance(el);
            modal.hide();

            return modal;
        });

        let errorModal = bootstrap.Modal.getOrCreateInstance(this.I("error-modal"), { "backdrop": "static" });

        this.I("error-modal-body").innerHTML = html; // SAFE (users need to be careful!)

        errorModal.show();
        errorModal._backdrop._element.style.backgroundColor = "red";

        this.I("error-modal").addEventListener("hidden.bs.modal", () => {
            shownModals.forEach(modal => modal.show());
        }, { once: true });
    },

    skipFromTesting() {
        const desiredShowPage = parseInt(this.selectedValue("uproot-skip"));

        this.api("skip", desiredShowPage).then(this.reload);
    },

    alert(html) {
        const shownModals = Array.from(document.querySelectorAll(".modal.show")).map(el => {
            const modal = bootstrap.Modal.getOrCreateInstance(el);
            modal.hide();

            return modal;
        });

        let alertModal = bootstrap.Modal.getOrCreateInstance(this.I("alert-modal"), { "backdrop": "static" });

        this.I("alert-modal-body").innerHTML = html; // SAFE (users need to be careful, and prefer window.alert()!)

        alertModal.show();

        this.I("alert-modal").addEventListener("hidden.bs.modal", () => {
            shownModals.forEach(modal => modal.show());
        }, { once: true });
    },

    sum(arr) {
        return arr.reduce((acc, val) => acc + val, 0);
    },

    mean(arr) {
        return this.sum(arr) / arr.length;
    },

    sd(arr) {
        const avg = this.mean(arr);
        const variance = arr.reduce((acc, val) => acc + Math.pow(val - avg, 2), 0) / (arr.length - 1);
        return Math.sqrt(variance);
    },

    escape(text) {
        const span = document.createElement("span");
        span.textContent = text;

        return span.innerHTML; // SAFE
    },

    ensureBuddy() {
        this.I("uproot-buddy").style.display = "block";
    },

    adminMessage(text) {
        const shownModals = Array.from(document.querySelectorAll(".modal.show")).map(el => {
            const modal = bootstrap.Modal.getOrCreateInstance(el);
            modal.hide();

            return modal;
        });

        let alertModal = bootstrap.Modal.getOrCreateInstance(this.I("adminmessage-modal"), { "backdrop": "static" });

        if (text !== undefined) {
            this.I("adminmessage-modal-body").innerText = text;
        }

        alertModal.show();

        this.I("adminmessage-modal").addEventListener("hidden.bs.modal", () => {
            shownModals.forEach(modal => modal.show());
        }, { once: true });

        this.ensureBuddy();
    },

    slidersWithoutAnchoring() {
        const sliders = document.querySelectorAll("input[type='range'].without-anchoring");

        sliders.forEach((slider) => {
            slider.value = "";

            // Create hidden input to track actual value
            const hiddenInput = document.createElement("input");
            hiddenInput.type = "hidden";
            hiddenInput.name = slider.name;
            hiddenInput.value = ""; // Empty until user interacts

            // Change slider name so it won't be submitted
            slider.name = slider.name + "_display";
            slider.insertAdjacentElement('afterend', hiddenInput);

            // Capture slider dimensions before hiding
            const sliderRect = slider.getBoundingClientRect();
            const computedStyle = window.getComputedStyle(slider);

            // Create wrapper with exact slider dimensions
            const wrapper = document.createElement("div");
            wrapper.style.cssText = `
            position: relative;
            display: inline-block;
            width: ${sliderRect.width || computedStyle.width}px;
            height: ${sliderRect.height || computedStyle.height}px;
        `;

            // Insert wrapper before slider and move slider into wrapper
            slider.parentNode.insertBefore(wrapper, slider);
            wrapper.appendChild(slider);

            const overlay = document.createElement("div");
            overlay.classList.add("without-anchoring-overlay");

            overlay.addEventListener("click", (e) => {
                const rect = overlay.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const percentage = clickX / rect.width;

                const min = parseFloat(slider.min) || 0;
                const max = parseFloat(slider.max) || 100;
                const value = min + (percentage * (max - min));

                slider.value = value;
                hiddenInput.value = value; // Set the value that will be submitted
                slider.dispatchEvent(new Event("input", { bubbles: true }));
                slider.dispatchEvent(new Event("change", { bubbles: true }));

                overlay.remove();
                slider.style.display = "block";
            });

            slider.style.display = "none";
            wrapper.appendChild(overlay);
        });
    },

    chat: {
        messageStore: {},

        create(el, chatId) {
            chatId = uproot.escape(chatId); // This utterly eviscerates everything suspicious

            el.innerHTML = /* SAFE */ `<div id="chat-${chatId}" class="uproot-chat chat-container hidden" data-chatid="${chatId}">
                <div class="messages-container border rounded bg-white mb-3" role="log" aria-label="Chat messages" aria-live="polite">
                    <ul class="list-unstyled mb-0 p-0" id="messages-chat-${chatId}">
                    </ul>
                </div>

                <div class="d-flex gap-2">
                    <label for="message-input-chat-${chatId}" class="visually-hidden">${_("Type your message")}</label>
                    <input type="text"
                           id="message-input-chat-${chatId}"
                           class="form-control"
                           placeholder="${_("Type your message")}"
                           required
                           autocomplete="off">
                    <button type="button" class="btn btn-primary" onclick="uproot.chat.sendMessage('${chatId}')" aria-label="Send message">Send</button>
                </div>
            </div>`;

            const ch = el.children[0];

            if (!this.messageStore[chatId]) {
                this.messageStore[chatId] = new Set();
            }

            uproot.api("chat_get", chatId).
                then(uproot.chat.messagesFromServer).
                then(() => {
                    ch.classList.remove("hidden");
                    ch.children[0].scroll(0, 1e6);
                });
        },

        addMessage(chatId, username, message, timestamp, cls = "text-primary") {
            if (!this.messageStore[chatId]) {
                this.messageStore[chatId] = new Set();
            }

            const escapedUsername = uproot.escape(username);
            const escapedMessage = uproot.escape(message);

            const messageKey = `${escapedUsername}:${escapedMessage}:${timestamp}`;

            if (this.messageStore[chatId].has(messageKey)) {
                return; // Skip duplicate message
            }

            this.messageStore[chatId].add(messageKey);

            const messagesList = document.querySelector(`#messages-chat-${chatId}`);
            if (!messagesList) {
                console.error(`Chat messages list not found for chatId: ${chatId}`);
                return;
            }

            const time = new Date(1000 * timestamp);
            const timeString = time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
            const isoString = time.toISOString();

            const messageElement = document.createElement("li");
            messageElement.className = "px-3 py-2 message-hover";
            messageElement.innerHTML = /* SAFE */ `
                        <div class="d-flex justify-content-between align-items-start mb-1">
                            <span class="fw-semibold ${cls} sender">${escapedUsername}</span>
                            <time class="text-muted small time" title="${isoString}" datetime="${isoString}">${timeString}</time>
                        </div>
                        <div class="text-break">${escapedMessage}</div>
                    `;

            messagesList.appendChild(messageElement);
            if (messagesList.parentElement) {
                messagesList.parentElement.scrollTop = messagesList.parentElement.scrollHeight;
            }
        },

        sendMessage(chatId) {
            const input = document.querySelector(`#message-input-chat-${chatId}`);

            if (!input) {
                console.error(`Chat input not found for chatId: ${chatId}`);
                return;
            }

            const message = input.value.trim();

            if (message) {
                input.value = "";

                window.uproot.api("chat_add", [chatId, message]);
            }
        },

        messagesFromServer(msgs) {
            if (msgs) {
                msgs.forEach((msg) => {
                    if (msg.cname && I(`chat-${msg.cname}`)) {
                        let senderRepresentation = msg.sender[1];
                        let colorCls = "text-success";

                        if (msg.sender[0] == "self") {
                            senderRepresentation = `${msg.sender[1]} (${_("You")})`;
                            colorCls = "text-primary";
                        }
                        else if (msg.sender[0] == "admin") {
                            senderRepresentation = _("Chat with Research Coordinator");
                            colorCls = "text-danger";
                        }

                        window.uproot.chat.addMessage(
                            msg.cname,
                            senderRepresentation,
                            msg.text,
                            msg.time,
                            colorCls,
                        );
                    }
                });
            }
        },
    },
};

window._ = (s) => {
    if (s in window.uproot.terms) {
        return window.uproot.terms[s];
    }
    else {
        if (this.verbose) {
            console.log(`Missing translation into of: '${s}'`);
        }

        return s;
    }
};

window.alert = (message) => {
    window.uproot.alert(uproot.escape(message));
};

window.I = (id_) => document.getElementById(id_);

uproot.onInternalEvent("Received", (event) => {
    const entry = event.detail;

    if (uproot.receive === null) {
        throw new Error(`Please define uproot.receive(). Ignored data received from server: ${JSON.stringify(entry.data)}`);
    }
    else {
        uproot.receive(entry.data);
    }
});

uproot.onInternalEvent("Chatted", (event) => {
    window.uproot.chat.messagesFromServer([event.detail.data]);
});

uproot.onInternalEvent("AdminMessaged", (event) => {
    const entry = event.detail;

    uproot.adminMessage(entry.data);
});
