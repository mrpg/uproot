uproot.simulate = {
    page() {
        return uproot.currentPage || uproot.vars?._uproot_internal?.thisis || null;
    },

    css(value) {
        if (window.CSS?.escape) return CSS.escape(String(value));
        return String(value).replace(/["\\]/g, "\\$&");
    },

    isPage(expected) {
        const page = this.page();
        const expectedPages = Array.isArray(expected) ? expected : [expected];

        return expectedPages.some((item) => {
            if (item instanceof RegExp) return item.test(page);
            if (typeof item === "function") return item(page);
            return page === item;
        });
    },

    assertPage(expected) {
        if (!this.isPage(expected)) {
            throw new Error(`Expected page ${JSON.stringify(expected)}, got ${JSON.stringify(this.page())}`);
        }

        return this;
    },

    on(expected, fn) {
        if (this.isPage(expected)) {
            fn(this);
            return true;
        }

        return false;
    },

    element(nameOrSelector) {
        const id = document.getElementById(nameOrSelector);
        if (id) return id;

        const escaped = this.css(nameOrSelector);
        const byName = document.querySelector(`[name="${escaped}"]`);
        if (byName) return byName;

        const bySelector = document.querySelector(nameOrSelector);
        if (bySelector) return bySelector;

        throw new Error(`Could not find form element ${JSON.stringify(nameOrSelector)}`);
    },

    field(nameOrSelector) {
        return this.element(nameOrSelector);
    },

    dispatch(el) {
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
    },

    fill(nameOrValues, value) {
        if (typeof nameOrValues === "object" && nameOrValues !== null) {
            Object.entries(nameOrValues).forEach(([name, fieldValue]) => this.fill(name, fieldValue));
            return this;
        }

        const el = this.field(nameOrValues);
        el.value = value;
        this.dispatch(el);

        return this;
    },

    choose(name, value) {
        const escapedName = this.css(name);
        const escapedValue = this.css(value);
        const radio = document.querySelector(`input[type="radio"][name="${escapedName}"][value="${escapedValue}"]`);
        if (radio) {
            radio.checked = true;
            this.dispatch(radio);
            return this;
        }

        const id = document.getElementById(`${name}-${value}`);
        if (id) {
            id.checked = true;
            this.dispatch(id);
            return this;
        }

        const select = document.querySelector(`select[name="${escapedName}"]`);
        if (select) {
            select.value = value;
            this.dispatch(select);
            return this;
        }

        throw new Error(`Could not choose ${JSON.stringify(value)} for ${JSON.stringify(name)}`);
    },

    check(name, value = true) {
        if (value !== true && value !== false) {
            return this.choose(name, value);
        }

        const el = this.field(name);
        el.checked = Boolean(value);
        this.dispatch(el);

        return this;
    },

    uncheck(name) {
        return this.check(name, false);
    },

    select(name, value) {
        return this.choose(name, value);
    },

    value(name) {
        const checked = document.querySelector(`input[name="${this.css(name)}"]:checked`);
        if (checked) return checked.value;

        return this.field(name).value;
    },

    oneOf(name, values) {
        return this.choose(name, this.random(values));
    },

    chooseAnyRadio(selector = 'input[type="radio"]') {
        const radios = Array.from(document.querySelectorAll(selector));
        if (radios.length === 0) {
            throw new Error(`uproot.simulate.chooseAnyRadio: no elements matched ${JSON.stringify(selector)}`);
        }
        const radio = this.random(radios);
        radio.checked = true;
        this.dispatch(radio);

        return this;
    },

    random(values) {
        if (!Array.isArray(values) || values.length === 0) {
            throw new Error("uproot.simulate.random expects a non-empty array");
        }

        return values[Math.floor(Math.random() * values.length)];
    },

    integer(min, max) {
        return min + Math.floor(Math.random() * (max - min + 1));
    },

    submit() {
        uproot.submit();
        return this;
    },
};
