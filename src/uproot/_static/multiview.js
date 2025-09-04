let zIndexCounter = 100;

function bringToFront(container) {
    container.style.zIndex = ++zIndexCounter;
}

function calculateGrid(count) {
    if (count === 1) return { cols: 1, rows: 1 };
    if (count <= 4) return { cols: 2, rows: 2 };
    if (count <= 9) return { cols: 3, rows: 3 };
    if (count <= 16) return { cols: 4, rows: 4 };
    const cols = Math.ceil(Math.sqrt(count));
    return { cols, rows: Math.ceil(count / cols) };
}

function createIframes(urls) {
    clearAll();
    if (!urls.length) return;

    const { cols, rows } = calculateGrid(urls.length);
    const containerWidth = window.innerWidth / cols;
    const containerHeight = window.innerHeight / rows;

    urls.forEach((url, index) => {
        const row = Math.floor(index / cols);
        const col = index % cols;

        const container = document.createElement("div");
        container.className = "iframe-container";
        container.style.left = `${col * containerWidth}px`;
        container.style.top = `${row * containerHeight}px`;
        container.style.width = `${containerWidth}px`;
        container.style.height = `${containerHeight}px`;

        const header = document.createElement("div");
        header.className = "iframe-header";
        header.textContent = url;

        const iframe = document.createElement("iframe");
        iframe.src = url;
        iframe.loading = "lazy";

        container.appendChild(header);
        container.appendChild(iframe);
        document.body.appendChild(container);

        makeDraggable(container, header);
        container.addEventListener("mousedown", () => bringToFront(container));
    });
}

function makeDraggable(container, handle) {
    let isDragging = false;
    let startX, startY, startLeft, startTop;

    handle.addEventListener("mousedown", (e) => {
        isDragging = true;
        container.classList.add("dragging");
        bringToFront(container);

        startX = e.clientX;
        startY = e.clientY;
        startLeft = parseInt(container.style.left, 10);
        startTop = parseInt(container.style.top, 10);

        e.preventDefault();
    });

    document.addEventListener("mousemove", (e) => {
        if (!isDragging) return;

        const deltaX = e.clientX - startX;
        const deltaY = e.clientY - startY;

        container.style.left = `${startLeft + deltaX}px`;
        container.style.top = `${startTop + deltaY}px`;
    });

    document.addEventListener("mouseup", () => {
        if (isDragging) {
            isDragging = false;
            container.classList.remove("dragging");
        }
    });
}

function clearAll() {
    document.querySelectorAll(".iframe-container").forEach(el => el.remove());
}
