class TableManager {
    constructor(tableId, active = true) {
        this.table = I(tableId);
        this.tbody = this.table.querySelector("tbody") || this.table.appendChild(document.createElement("tbody"));
        this.thead = this.table.querySelector("thead") || this.table.insertBefore(document.createElement("thead"), this.tbody);
        this.headerRow = this.thead.querySelector("tr") || this.thead.appendChild(document.createElement("tr"));
        this.columns = new Set();
        this.rows = new Map();
        this.active = active;

        // NEW: track original insertion order so we can restore it
        this._rowSequence = 0;
    }

    getCell(rowId, colId) {
        this._ensureColumn(colId);
        const row = this._ensureRow(rowId);
        const cell = this._getCell(row, colId);

        if (this.active) {
            cell.classList.add("table-active");
            setTimeout(() => cell.classList.remove("table-active"), 1000);
        }

        return cell;
    }

    _ensureColumn(colId) {
        if (this.columns.has(colId)) return;

        this.columns.add(colId);
        const th = document.createElement("th");
        th.dataset.colId = colId;

        // Header label container + sort indicator
        const label = document.createElement("span");
        label.className = "th-label";

        if (colId.length > 28) {
            label.textContent = `${colId.substr(0, 28)}…`;
        }
        else {
            label.textContent = colId;
        }

        const indicator = document.createElement("span");
        indicator.className = "sort-indicator"; // will show ascending/descending indicators
        indicator.style.marginLeft = "0.35em";
        indicator.innerHTML = "&#9676;"; // SAFE

        th.appendChild(label);
        th.appendChild(indicator);

        // Make header clickable & accessible
        th.classList.add("sortable");
        th.setAttribute("role", "button");
        th.setAttribute("tabindex", "0");
        th.dataset.sortState = "original"; // original -> asc -> desc -> original
        th.addEventListener("click", () => {
            if (th.classList.contains("sortable")) {
                this._toggleSort(colId);
            };
        });
        th.addEventListener("keydown", (e) => {
            if (th.classList.contains("sortable") && (e.key === "Enter" || e.key === " ")) {
                e.preventDefault();
                this._toggleSort(colId);
            }
        });

        this.headerRow.appendChild(th);

        // ensure every existing row gets a td for this new column
        this.rows.forEach(row => {
            const td = document.createElement("td");
            td.dataset.colId = colId;
            row.appendChild(td);
        });
    }

    _ensureRow(rowId) {
        if (this.rows.has(rowId)) return this.rows.get(rowId);

        const tr = document.createElement("tr");
        tr.dataset.rowId = rowId;

        // mark original order index ONCE, when row is created
        tr.dataset.originalIndex = String(this._rowSequence++);
        // (kept) create all existing columns as TDs
        this.columns.forEach(colId => {
            const td = document.createElement("td");
            td.dataset.colId = colId;
            tr.appendChild(td);
        });

        const insertionPoint = this._findInsertionPoint(rowId);
        if (insertionPoint) {
            this.tbody.insertBefore(tr, insertionPoint);
        } else {
            this.tbody.appendChild(tr);
        }

        this.rows.set(rowId, tr);
        return tr;
    }

    _findInsertionPoint(rowId) {
        const existingRows = Array.from(this.tbody.children);
        for (const row of existingRows) {
            if (row.dataset.rowId > rowId) {
                return row;
            }
        }
        return null;
    }

    _getCell(row, colId) {
        return row.querySelector(`td[data-col-id="${colId}"]`);
    }

    // ===== Sorting helpers =====

    _toggleSort(colId) {
        const th = this._getHeaderCell(colId);
        const current = th?.dataset.sortState || "original";
        const next = current === "original" ? "asc" : current === "asc" ? "desc" : "original";
        this._applySort(colId, next);
    }

    _applySort(colId, direction) {
        // Update header states/indicators
        this._updateHeaderStates(colId, direction);

        const rows = Array.from(this.tbody.querySelectorAll("tr"));
        if (direction === "original") {
            rows.sort((a, b) => Number(a.dataset.originalIndex) - Number(b.dataset.originalIndex));
        } else {
            rows.sort((a, b) => this._compareRows(a, b, colId, direction));
        }

        // Rebuild tbody with the new row order (reshape WHOLE table)
        const frag = document.createDocumentFragment();
        rows.forEach(r => frag.appendChild(r));
        this.tbody.appendChild(frag);
    }

    _compareRows(a, b, colId, direction) {
        const av = this._getCellText(a, colId);
        const bv = this._getCellText(b, colId);

        // Handle empties like Wikipedia: empty strings sort last in ascending, first in descending
        const aEmpty = av === "";
        const bEmpty = bv === "";
        if (aEmpty && bEmpty) return 0;
        if (aEmpty) return direction === "asc" ? 1 : -1;
        if (bEmpty) return direction === "asc" ? -1 : 1;

        // Try numeric compare; fallback to case-insensitive string compare
        const an = this._toNumber(av);
        const bn = this._toNumber(bv);

        let cmp;
        if (!Number.isNaN(an) && !Number.isNaN(bn)) {
            cmp = an - bn;
        } else {
            // localeCompare for human-ish ordering; case-insensitive
            cmp = av.localeCompare(bv, undefined, { numeric: true, sensitivity: "base" });
        }

        return direction === "asc" ? cmp : -cmp;
    }

    _getCellText(row, colId) {
        const cell = row.querySelector(`td[data-col-id="${colId}"]`);
        if (!cell) return "";
        // Prefer data-sort-value if present (like Wikipedia), else textContent
        const explicit = cell.getAttribute("data-sort-value");
        return (explicit ?? cell.textContent ?? "").trim();
    }

    _toNumber(v) {
        // Strip common number noise (commas, spaces)
        const cleaned = v.replace(/[,\s]/g, "");

        // Check if the cleaned value is a valid numeric literal
        // Accepts optional sign, digits, optional decimal, optional exponent
        if (!/^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$/.test(cleaned)) {
            return NaN;
        }

        const n = parseFloat(cleaned);
        return Number.isFinite(n) ? n : NaN;
    }

    _getHeaderCell(colId) {
        return this.headerRow.querySelector(`th[data-col-id="${colId}"]`);
    }

    _updateHeaderStates(activeColId, direction) {
        // Clear all indicators
        const ths = Array.from(this.headerRow.querySelectorAll("th[data-col-id]"));
        ths.forEach(th => {
            const ind = th.querySelector(".sort-indicator");
            if (th.dataset.colId === activeColId) {
                th.dataset.sortState = direction;
                th.setAttribute("aria-sort",
                    direction === "asc" ? "ascending" :
                        direction === "desc" ? "descending" : "none");
                if (ind) ind.innerHTML = direction === "asc" ? "&#9650;" : direction === "desc" ? "&#9660;" : "&#9676;"; // SAFE
            } else {
                th.dataset.sortState = "original";
                th.setAttribute("aria-sort", "none");
                if (ind) ind.innerHTML = "&#9676;"; // SAFE
            }
        });
    }
}
