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
    dirty: false,
    form: null,
    futStore: {},
    I: (id_) => document.getElementById(id_),
    isInitialized: false,
    keepAliveInterval: null,
    key: null,
    missing: new Set(),
    receive: null,
    root: null,
    serverThere: null,
    sname: null,
    terms: {},
    testing: false,
    timeout1: null,
    timeout2: null,
    timeoutUntil: null,
    uname: null,
    vars: {},
    verbose: false,
    ws: null,

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

        const days = Math.floor(remainingSeconds / 86400);
        const hours = Math.floor((remainingSeconds % 86400) / 3600);
        const minutes = Math.floor((remainingSeconds % 3600) / 60);
        const seconds = Math.floor(remainingSeconds % 60);

        const parts = [];
        if (days > 0) parts.push(_(days === 1 ? "#x# day" : "#x# days").replace("#x#", days));
        if (hours > 0) parts.push(_(hours === 1 ? "#x# hour" : "#x# hours").replace("#x#", hours));
        if (minutes > 0) parts.push(_(minutes === 1 ? "#x# minute" : "#x# minutes").replace("#x#", minutes));
        if (seconds > 0 || parts.length === 0) parts.push(_(seconds === 1 ? "#x# second" : "#x# seconds").replace("#x#", seconds));

        const timeText = parts.length > 1
            ? parts.slice(0, -1).join(_(", ")) + _(" and ") + parts[parts.length - 1]
            : parts[0];

        if (I("uproot-time-remaining")) {
            I("uproot-time-remaining").innerText = timeText;
        }

        if (I("uproot-timeout")) {
            I("uproot-timeout").hidden = false;

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
        }

        window.dispatchEvent(new CustomEvent(`UprootInternalPageTimeout`));
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
        const processMessage = (rawJson) => {
            const msg = Object.assign({ received: Date.now() }, JSON.parse(rawJson));
            const kind = msg.kind, payload = msg.payload;
            const currentPage = this.vars?._uproot_internal?.thisis || null;

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
                else if (action == "redirect" && "url" in payload) {
                    this.redirect(payload.url);
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
                if (!("constraint" in payload.entry) || payload.entry.constraint === null || payload.entry.constraint == currentPage) {
                    this.queueDispatch(payload.u, payload.entry);
                }
            }
        };

        // Handle both string and Blob message data
        if (typeof event.data === "string") {
            processMessage(event.data);
        }
        else {
            event.data.text().then(processMessage).catch(() => {
                // Blob may become unreadable under heavy load; silently ignore
            });
        }
    },

    isValidToken(x) {
        if (typeof x !== "string") return false;
        return /^[a-zA-Z0-9._-]+$/.test(x);
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
                if (this.keepAliveInterval !== null) {
                    window.clearInterval(this.keepAliveInterval);
                }
                this.keepAliveInterval = window.setInterval(this.hello, 9000);

                this.hello().then(() => {
                    if (!this.isInitialized) {
                        this.isInitialized = true;
                        window.dispatchEvent(new Event("UprootReady"));
                    }
                    else {
                        window.dispatchEvent(new Event("UprootReconnect"));
                    }
                });
            },
            onMessage: (event, ws) => {
                this.fromServer(event, ws);
            },
            onClose: (event, ws) => {
                window.dispatchEvent(new Event("UprootDisconnect"));
            },
        });
    },

    csrf() {
        return `${this.sname}+${this.uname}+${this.key}`;
    },

    init() {
        this.sname = uproot.vars._uproot_internal.sname;
        this.uname = uproot.vars._uproot_internal.uname;
        this.root = uproot.vars._uproot_internal.root;
        this.key = uproot.vars._uproot_internal.key;
        this.form = document.forms[0];

        this.I("_uproot_from").value = uproot.vars._uproot_internal.thisis;
        this.I("_uproot_csrf").value = this.csrf();
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
        return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
            const r = Math.random() * 16 | 0;
            const v = c === "x" ? r : (r & 0x3 | 0x8);
            return v.toString(16);
        });
    },

    reload() {
        // this "works" even with POST - skips confirmation
        document.location = document.location;
    },

    redirect(url) {
        if (url.startsWith("http://") || url.startsWith("https://")) {
            document.location = url;
        }
    },

    submit() {
        return I("uproot-form").submit();
    },

    goBack() {
        this.I("_uproot_from").value = "back-" + uproot.vars._uproot_internal.thisis;
        return I("uproot-form").submit();
    },

    onStart(fun) {
        if (document.readyState === "loading") {
            window.addEventListener("DOMContentLoaded", fun);
        }
        else {
            fun();
        }
    },

    onReady(fun) {
        if (!this.isInitialized) {
            window.addEventListener("UprootReady", fun);
        }
        else {
            fun();
        }
    },

    onReconnect(fun) {
        window.addEventListener("UprootReconnect", fun);
    },

    onDisconnect(fun) {
        window.addEventListener("UprootDisconnect", fun);
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

    prompt(html, value = "") {
        return new Promise((resolve) => {
            const shownModals = Array.from(document.querySelectorAll(".modal.show")).map(el => {
                const modal = bootstrap.Modal.getOrCreateInstance(el);
                modal.hide();

                return modal;
            });

            let alertModal = bootstrap.Modal.getOrCreateInstance(this.I("alert-modal"), { "backdrop": "static" });

            // Create the prompt content with input field
            const inputId = "uproot-prompt-input-" + this.uuid();
            this.I("alert-modal-body").innerHTML = `${html}<input type="text" id="${inputId}" class="form-control mt-3" autocomplete="off">`; // SAFE (users need to be careful!)

            const inputElement = this.I(inputId);

            // Modify the existing button to be a non-outlined OK button
            const existingButton = this.I("alert-modal").querySelector('.modal-footer button');
            if (existingButton) {
                existingButton.className = "btn btn-uproot";
                existingButton.textContent = _("OK");
                existingButton.removeAttribute('data-bs-dismiss');
            }

            const handleResponse = (value) => {
                alertModal.hide();
                resolve(value);
            };

            const handleOkClick = () => {
                const value = inputElement.value;
                handleResponse(value);
            };

            const handleKeydown = (e) => {
                if (e.key === "Enter") {
                    e.preventDefault();
                    const value = inputElement.value;
                    handleResponse(value);
                }
                else if (e.key === "Escape") {
                    e.preventDefault();
                    handleResponse(null);
                }
            };

            // Add event listeners
            inputElement.addEventListener("keydown", handleKeydown);
            if (existingButton) {
                existingButton.addEventListener("click", handleOkClick);
            }

            I(inputId).value = value;
            alertModal.show();

            // Focus the input after modal is shown
            this.I("alert-modal").addEventListener("shown.bs.modal", () => {
                inputElement.focus();
            }, { once: true });

            this.I("alert-modal").addEventListener("hidden.bs.modal", () => {
                // Clean up event listeners and restore original button
                inputElement.removeEventListener("keydown", handleKeydown);
                if (existingButton) {
                    existingButton.removeEventListener("click", handleOkClick);
                    existingButton.className = "btn btn-outline-uproot";
                    existingButton.textContent = _("Close");
                    existingButton.setAttribute('data-bs-dismiss', 'modal');
                }
                shownModals.forEach(modal => modal.show());
            }, { once: true });
        });
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

    /**
     * Evaluates a JavaScript expression and returns its JSON representation.
     *
     * This function intentionally uses eval() to allow rich expressions in admin
     * settings input, including comments, calculations, and variables. This is
     * admin-only functionality - never expose this to untrusted input.
     *
     * Examples of supported input:
     *   { speed: 2 * 50, name: "test" }
     *   { items: [1, 2, 3], }  // trailing commas and JS comments OK
     *
     * @param {string} input - JavaScript expression that evaluates to an object
     * @returns {string} JSON string representation of the evaluated object
     * @throws {SyntaxError} If the input cannot be parsed as JavaScript
     * @throws {TypeError} If the result cannot be serialized to JSON
     */
    looseJSONtoJSON(input) {
        // SECURITY NOTE: eval() is used intentionally here for admin convenience.
        // This allows JS expressions (calculations, comments, etc.) in settings.
        // This function must NEVER be exposed to untrusted user input.
        const obj = eval("(" + input + ")");
        return JSON.stringify(obj);
    },

    ensureBuddy() {
        this.I("uproot-buddy").hidden = false;
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
            // Remove the name attribute so this slider won't be submitted
            const originalName = slider.name;
            slider.removeAttribute("name");

            // Create a hidden input to track interaction
            const hiddenInput = document.createElement("input");
            hiddenInput.type = "hidden";
            hiddenInput.name = originalName;
            hiddenInput.value = ""; // Empty until user interacts
            slider.insertAdjacentElement("afterend", hiddenInput);

            // Mark slider as uninteracted
            slider.dataset.interacted = "false";

            // Function to calculate step-aligned value from click position
            const calculateSteppedValue = (clickX, sliderRect) => {
                // Parse slider attributes with proper defaults
                const min = parseFloat(slider.min) || 0;
                const max = parseFloat(slider.max) || 100;
                let step = parseFloat(slider.step);

                // Handle step="any" or invalid step
                if (isNaN(step) || step <= 0 || slider.step === "any") {
                    step = 1; // Default step
                }

                // Handle edge case where max < min
                if (max <= min) {
                    return min;
                }

                // Handle zero width (shouldn't happen but be safe)
                if (sliderRect.width <= 0) {
                    return min;
                }

                // Calculate percentage of click position, clamped to [0,1]
                const percentage = Math.max(0, Math.min(1, clickX / sliderRect.width));

                // Calculate raw value based on percentage
                const rawValue = min + (percentage * (max - min));

                // Calculate step base according to HTML spec
                // Step base is min if specified, otherwise 0
                const stepBase = isNaN(parseFloat(slider.min)) ? 0 : min;

                // Calculate number of steps from base
                // Round to nearest step (HTML spec: "preferring to round numbers up when there are two equally close options")
                const stepsFromBase = Math.round((rawValue - stepBase) / step);

                // Calculate final stepped value
                let steppedValue = stepBase + (stepsFromBase * step);

                // Handle floating point precision issues
                steppedValue = Math.round(steppedValue / step) * step;

                // Ensure value is within bounds
                steppedValue = Math.max(min, Math.min(max, steppedValue));

                // Final validation: ensure the value is actually valid according to step
                const finalStepsFromBase = Math.round((steppedValue - stepBase) / step);
                const validatedValue = stepBase + (finalStepsFromBase * step);

                return Math.max(min, Math.min(max, validatedValue));
            };

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

            // Create overlay to hide slider and capture clicks
            const overlay = document.createElement("div");
            overlay.classList.add("without-anchoring-overlay");

            // Hide slider initially and reset width
            slider.style.display = "none";
            slider.classList.remove("w-50");

            // Add overlay click handler
            overlay.addEventListener("click", (e) => {
                const rect = overlay.getBoundingClientRect();
                const clickX = e.clientX - rect.left;
                const steppedValue = calculateSteppedValue(clickX, rect);

                // Set the calculated step-aligned value
                slider.value = steppedValue;
                slider.dataset.interacted = "true";
                hiddenInput.value = steppedValue;

                // Remove overlay and reveal slider
                overlay.remove();
                slider.style.display = "block";

                // Dispatch events for consistency
                slider.dispatchEvent(new Event("input", { bubbles: true }));
                slider.dispatchEvent(new Event("change", { bubbles: true }));
            });

            // Add overlay to wrapper
            wrapper.appendChild(overlay);

            // Add event listeners to track further direct interaction and update hidden input
            const handleDirectInteraction = () => {
                slider.dataset.interacted = "true";
                hiddenInput.value = slider.value;
            };

            slider.addEventListener("input", handleDirectInteraction);
            slider.addEventListener("change", handleDirectInteraction);
        });
    },

    nonRequiredRadios() {
        // Inject CSS once
        if (!document.getElementById("radio-toggle-clear-style")) {
            const style = document.createElement("style");
            style.id = "radio-toggle-clear-style";
            style.textContent = `
                .form-check.radio-toggle-clear-hover > .form-check-label {
                    color: var(--bs-dark-bg-subtle);
                    text-decoration: line-through;
                    text-decoration-color: var(--bs-dark-bg-subtle);
                    text-decoration-thickness: from-font;
                    cursor: pointer;
                }
            `;
            document.head.appendChild(style);
        }
        const TOOLTIP_TEXT = _("Click again to unselect.");
        document.querySelectorAll("input[type='radio']:not([required])").forEach((radio) => {
            // Prevent double-binding
            if (radio.dataset.toggleClearBound === "1") return;
            radio.dataset.toggleClearBound = "1";
            const formCheck = radio.closest(".form-check");
            const label =
            formCheck?.querySelector(`label.form-check-label[for="${CSS.escape(radio.id)}"]`) ||
            radio.closest("label") ||
            document.querySelector(`label[for="${CSS.escape(radio.id)}"]`);
            /* ---------- Hover cue + tooltip ---------- */
            if (formCheck) {
                formCheck.addEventListener("mouseenter", () => {
                    if (!radio.required && radio.checked) {
                    formCheck.classList.add("radio-toggle-clear-hover");
                    formCheck.title = TOOLTIP_TEXT;
                    }
                });
                formCheck.addEventListener("mouseleave", () => {
                    formCheck.classList.remove("radio-toggle-clear-hover");
                    formCheck.removeAttribute("title");
                });
                // Keep things correct if state changes via keyboard/code
                radio.addEventListener("change", () => {
                    formCheck.classList.remove("radio-toggle-clear-hover");
                    formCheck.removeAttribute("title");
                });
            }
            /* ---------- Label behavior (capture phase) ---------- */
            if (label) {
                label.addEventListener(
                    "pointerdown",
                    () => {
                    radio.dataset.preChecked = radio.checked ? "1" : "0";
                    },
                    true
                );
                label.addEventListener(
                    "click",
                    (e) => {
                    if (radio.required) return;
                    const preChecked = radio.dataset.preChecked === "1";
                    radio.dataset.preChecked = "0";
                    if (!preChecked) return; // normal selection
                        e.preventDefault();
                        e.stopPropagation();
                        radio.checked = false;
                        radio.dispatchEvent(new Event("change", { bubbles: true }));
                    },
                    true
                );
            }
            /* ---------- Input behavior (must clear on pointerdown) ---------- */
            radio.addEventListener(
                "pointerdown",
                (e) => {
                    radio.dataset.preChecked = radio.checked ? "1" : "0";
                    // Clicking the already-checked radio itself
                    if (!radio.required && radio.checked) {
                    e.preventDefault();
                    e.stopPropagation();
                    radio.checked = false;
                    radio.dispatchEvent(new Event("change", { bubbles: true }));
                    }
                },
                true
            );
            radio.addEventListener(
                "click",
                (e) => {
                    if (radio.required) return;

                    if (radio.dataset.preChecked === "1") {
                    e.preventDefault();
                    e.stopPropagation();
                    }
                    radio.dataset.preChecked = "0";
                },
                true
            );
            /* ---------- Keyboard support ---------- */
            radio.addEventListener("keydown", (e) => {
            if (e.key === " " || e.key === "Spacebar") {
                if (!radio.required && radio.checked) {
                    e.preventDefault();
                    radio.checked = false;
                    radio.dispatchEvent(new Event("change", { bubbles: true }));
                }
            }
            });
        });
    },

    boundedChoiceFields() {
        document.querySelectorAll(".uproot-bounded-choice").forEach(container => {
            const minAttr = container.dataset.boundedMin;
            const maxAttr = container.dataset.boundedMax;
            const min = minAttr !== "" ? parseInt(minAttr, 10) : 0;
            const max = maxAttr !== "" ? parseInt(maxAttr, 10) : null;
            const checkboxes = container.querySelectorAll("input[type='checkbox']");

            const updateState = () => {
                const checkedCount = Array.from(checkboxes).filter(cb => cb.checked).length;

                // If max is reached, disable unchecked checkboxes
                if (max !== null && checkedCount >= max) {
                    checkboxes.forEach(cb => {
                        if (!cb.checked) {
                            cb.disabled = true;
                        }
                    });
                } else {
                    checkboxes.forEach(cb => {
                        cb.disabled = false;
                    });
                }
            };

            checkboxes.forEach(cb => {
                cb.addEventListener("change", updateState);
            });

            // Initialize state
            updateState();
        });
    },

    enableConnectionLostModal() {
        let connectionModal = null;
        let timeoutTimer = null;
        let startupTimer = null;
        let isPageUnloading = false;

        // Track when user is leaving the page
        window.addEventListener("beforeunload", () => {
            isPageUnloading = true;
        });

        const ensureConnectionModal = () => {
            if (!connectionModal) {
                connectionModal = bootstrap.Modal.getOrCreateInstance(
                    I("connection-timeout-modal"),
                    { backdrop: "static", keyboard: false }
                );
            }
            return connectionModal;
        };

        const showConnectionLostModal = () => {
            if (isPageUnloading) return;

            const modal = ensureConnectionModal();

            // Show/hide reload button based on dirty state
            const reloadBtn = I("connection-modal-reload-btn");

            if (reloadBtn) {
                reloadBtn.hidden = this.dirty;
            }

            modal.show();
            modal._backdrop._element.style.backgroundColor = "red";
        };

        const hideConnectionLostModal = () => {
            clearTimeout(startupTimer);
            if (connectionModal) {
                connectionModal.hide();
                connectionModal = null;
            }
        };

        // Startup failsafe: if isInitialized is still false after 10 seconds,
        // something went wrong (init failed, wsstart failed, WS never connected, etc.)
        startupTimer = setTimeout(() => {
            if (!this.isInitialized) {
                showConnectionLostModal();
            }
        }, 10000);

        // Wrap hello() to monitor connection health
        const originalHello = this.hello.bind(this);

        this.hello = function() {
            const sentAt = Date.now();

            // Clear any previous timeout
            clearTimeout(timeoutTimer);

            // Check for response within timeout window
            timeoutTimer = setTimeout(() => {
                if (!uproot.serverThere || uproot.serverThere < sentAt) {
                    showConnectionLostModal();
                }
            }, 1500);

            return originalHello();
        };

        // Hide modal on any server response
        const originalFromServer = this.fromServer.bind(this);

        this.fromServer = function(event, ws) {
            hideConnectionLostModal();
            return originalFromServer(event, ws);
        };

        // Show modal on WebSocket disconnect/error (but not when leaving page)
        this.onDisconnect(() => {
            if (!isPageUnloading) {
                showConnectionLostModal();
            }
        });
    },

    chat: {
        messageStore: {},
        ignoreChatted: true,

        handleChatKeydown(event, chatId) {
            if (event.key === "Enter") {
                event.preventDefault();
                this.sendMessage(chatId);
            }
        },

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
            const input = ch.querySelector(`#message-input-chat-${chatId}`);

            if (input) {
                input.addEventListener("keydown", (e) => this.handleChatKeydown(e, chatId));
            }

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

        addMessage(chatId, msgId, username, message, timestamp, cls = "text-primary") {
            if (!this.messageStore[chatId]) {
                this.messageStore[chatId] = new Set();
            }

            const escapedUsername = uproot.escape(username);
            const escapedMessage = uproot.escape(message);

            if (this.messageStore[chatId].has(msgId)) {
                return; // Skip duplicate message
            }

            this.messageStore[chatId].add(msgId);

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
                            msg.id,
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
        window.uproot.missing.add(s);

        if (window.uproot.verbose) {
            console.log(`Missing translation for: "${s}"`);
        }

        return s;
    }
};

window.alert = (message) => {
    window.uproot.alert(uproot.escape(message));
};

window.prompt = (message) => {
    return window.uproot.prompt(uproot.escape(message));
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
    if (!window.uproot.chat.ignoreChatted) {
        // This prevents style asyncio.Queue chat messages from being processed
        window.uproot.chat.messagesFromServer([event.detail.data]);
    }
});

uproot.onInternalEvent("AdminMessaged", (event) => {
    const entry = event.detail;

    uproot.adminMessage(entry.data);
});
