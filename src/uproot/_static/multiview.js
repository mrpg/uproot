class MultiviewManager {
    constructor() {
        this.containers = new Map();
        this.zIndexCounter = 100;
        this.isDragging = false;
        this.isResizing = false;
        this.dragState = {};
        this.resizeState = {};

        this.setupEventListeners();
        this.setupStyles();
    }

    setupStyles() {
        document.body.style.margin = '0';
        document.body.style.padding = '0';
        document.body.style.overflow = 'hidden';
        document.body.style.height = '100vh';
        document.body.style.width = '100vw';

        document.documentElement.style.overflow = 'hidden';
        document.documentElement.style.height = '100vh';
        document.documentElement.style.width = '100vw';
    }

    setupEventListeners() {
        this.handleMouseMove = this.handleMouseMove.bind(this);
        this.handleMouseUp = this.handleMouseUp.bind(this);
        this.handlePointerMove = this.handlePointerMove.bind(this);
        this.handlePointerUp = this.handlePointerUp.bind(this);
        this.handleWindowResize = this.handleWindowResize.bind(this);

        window.addEventListener('resize', this.handleWindowResize);
    }

    bringToFront(container) {
        container.style.zIndex = ++this.zIndexCounter;
    }

    createOverlay() {
        if (this.overlay) return;

        this.overlay = document.createElement('div');
        this.overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background: transparent;
            z-index: 999999;
            cursor: inherit;
            pointer-events: auto;
        `;
        document.body.appendChild(this.overlay);
    }

    removeOverlay() {
        if (this.overlay) {
            this.overlay.remove();
            this.overlay = null;
        }
    }

    calculateGrid(count) {
        if (count === 1) return { cols: 1, rows: 1 };
        if (count === 2) return { cols: 2, rows: 1 };
        if (count <= 4) return { cols: 2, rows: 2 };
        if (count <= 6) return { cols: 3, rows: 2 };
        if (count <= 9) return { cols: 3, rows: 3 };
        if (count <= 12) return { cols: 4, rows: 3 };
        if (count <= 16) return { cols: 4, rows: 4 };

        const cols = Math.ceil(Math.sqrt(count));
        return { cols, rows: Math.ceil(count / cols) };
    }

    createIframes(ids, labels, urls) {
        if (!urls.length) return;

        const { cols, rows } = this.calculateGrid(urls.length);
        const containerWidth = window.innerWidth / cols;
        const containerHeight = window.innerHeight / rows;

        for (let i = 0; i < urls.length; i++) {
            const row = Math.floor(i / cols);
            const col = i % cols;

            const container = this.createContainer(
                ids[i],
                labels[i] == "" ? "<span class='text-body-tertiary'>N/A</span>": uproot.escape(labels[i]),
                urls[i],
                col * containerWidth,
                row * containerHeight,
                containerWidth,
                containerHeight
            );

            this.containers.set(container.id, container);
        };
    }

    createContainer(id, label, url, x, y, width, height) {
        const container = document.createElement('div');
        container.className = 'iframe-container';
        container.id = 'container-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);

        container.style.position = 'absolute';
        container.style.left = `${x}px`;
        container.style.top = `${y}px`;
        container.style.width = `${width}px`;
        container.style.height = `${height}px`;

        const header = document.createElement('div');
        header.className = 'iframe-header';

        const titleSpan = document.createElement('span');
        titleSpan.className = 'iframe-title';
        titleSpan.innerHTML =
            `<b>ID <span class="font-monospace">${id}</span></b> <span class="fw-light"><span class="text-body-tertiary">&nbsp;|&nbsp;</span> Label <span class="font-monospace">${label}</span> <span class="text-body-tertiary">&nbsp;|&nbsp;</span> URL ${this.getDisplayName(url)}</span>`;

        const reloadButton = document.createElement('button');
        reloadButton.className = 'reload-button';
        reloadButton.innerHTML = '↻';
        reloadButton.title = 'Reload iframe';

        header.appendChild(titleSpan);
        header.appendChild(reloadButton);

        const iframe = document.createElement('iframe');
        iframe.src = url;
        iframe.loading = 'lazy';

        container.appendChild(header);
        container.appendChild(iframe);
        document.body.appendChild(container);

        this.setupContainerEvents(container, header, reloadButton, iframe);

        return container;
    }

    getDisplayName(url) {
        try {
            const urlObj = new URL(url);
            const pathParts = urlObj.pathname.split('/').filter(Boolean);
            return pathParts.length > 0 ? pathParts[pathParts.length - 1] : url;
        } catch {
            return url;
        }
    }

    setupContainerEvents(container, header, reloadButton, iframe) {
        container.addEventListener('mousedown', (e) => {
            if (e.target === reloadButton) return;
            this.bringToFront(container);
        });

        // Use both mouse and pointer events for better compatibility
        header.addEventListener('mousedown', (e) => {
            if (e.target === reloadButton) return;
            this.startDrag(e, container, 'mouse');
        });

        header.addEventListener('pointerdown', (e) => {
            if (e.pointerType === 'mouse' || e.target === reloadButton) return; // Avoid double handling
            this.startDrag(e, container, 'pointer');
        });

        // Add resize functionality to the container borders
        container.addEventListener('mousemove', (e) => {
            if (this.isDragging || this.isResizing) return;
            const rect = container.getBoundingClientRect();
            const isNearRightEdge = e.clientX > rect.right - 10;
            const isNearBottomEdge = e.clientY > rect.bottom - 10;

            if (isNearRightEdge && isNearBottomEdge) {
                container.style.cursor = 'se-resize';
            } else if (isNearRightEdge) {
                container.style.cursor = 'e-resize';
            } else if (isNearBottomEdge) {
                container.style.cursor = 's-resize';
            } else {
                container.style.cursor = '';
            }
        });

        container.addEventListener('mouseleave', () => {
            if (!this.isDragging && !this.isResizing) {
                container.style.cursor = '';
            }
        });

        container.addEventListener('mousedown', (e) => {
            if (e.target === reloadButton) return;
            const rect = container.getBoundingClientRect();
            const isNearRightEdge = e.clientX > rect.right - 10;
            const isNearBottomEdge = e.clientY > rect.bottom - 10;

            if (isNearRightEdge || isNearBottomEdge) {
                e.stopPropagation();
                this.startResize(e, container, 'mouse');
            }
        });

        container.addEventListener('pointerdown', (e) => {
            if (e.pointerType === 'mouse' || e.target === reloadButton) return;
            const rect = container.getBoundingClientRect();
            const isNearRightEdge = e.clientX > rect.right - 10;
            const isNearBottomEdge = e.clientY > rect.bottom - 10;

            if (isNearRightEdge || isNearBottomEdge) {
                e.stopPropagation();
                this.startResize(e, container, 'pointer');
            }
        });

        reloadButton.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            this.reloadIframe(iframe);
        });
    }

    reloadIframe(iframe) {
        const currentSrc = iframe.src;
        iframe.src = 'about:blank';
        setTimeout(() => {
            iframe.src = currentSrc;
        }, 100);
    }

    startDrag(e, container, eventType = 'mouse') {
        e.preventDefault();
        this.isDragging = true;
        this.eventType = eventType;
        this.bringToFront(container);
        container.classList.add('dragging');

        const rect = container.getBoundingClientRect();
        this.dragState = {
            container,
            startX: e.clientX || e.pageX,
            startY: e.clientY || e.pageY,
            startLeft: rect.left,
            startTop: rect.top,
            element: e.target
        };

        // Create overlay to prevent iframe interference
        this.createOverlay();

        if (eventType === 'pointer' && e.setPointerCapture) {
            e.target.setPointerCapture(e.pointerId);
            e.target.addEventListener('pointermove', this.handlePointerMove);
            e.target.addEventListener('pointerup', this.handlePointerUp);
        } else {
            // Use window instead of document for more reliable capture
            window.addEventListener('mousemove', this.handleMouseMove, { passive: false, capture: true });
            window.addEventListener('mouseup', this.handleMouseUp, { passive: false, capture: true });
        }

        // Prevent text selection and scrolling
        document.body.style.userSelect = 'none';
        document.body.style.overflow = 'hidden';
        e.target.style.cursor = 'grabbing';
    }

    startResize(e, container, eventType = 'mouse') {
        e.preventDefault();
        e.stopPropagation();
        this.isResizing = true;
        this.eventType = eventType;
        this.bringToFront(container);
        container.classList.add('resizing');

        const rect = container.getBoundingClientRect();
        this.resizeState = {
            container,
            startX: e.clientX || e.pageX,
            startY: e.clientY || e.pageY,
            startWidth: rect.width,
            startHeight: rect.height,
            startLeft: rect.left,
            startTop: rect.top,
            element: e.target
        };

        // Create overlay to prevent iframe interference
        this.createOverlay();

        if (eventType === 'pointer' && e.setPointerCapture) {
            e.target.setPointerCapture(e.pointerId);
            e.target.addEventListener('pointermove', this.handlePointerMove);
            e.target.addEventListener('pointerup', this.handlePointerUp);
        } else {
            // Use window instead of document for more reliable capture
            window.addEventListener('mousemove', this.handleMouseMove, { passive: false, capture: true });
            window.addEventListener('mouseup', this.handleMouseUp, { passive: false, capture: true });
        }

        // Prevent text selection and scrolling
        document.body.style.userSelect = 'none';
        document.body.style.overflow = 'hidden';
        e.target.style.cursor = 'se-resize';
    }

    handleMouseMove(e) {
        e.preventDefault();
        if (this.isDragging && this.dragState.container) {
            this.updateDrag(e);
        } else if (this.isResizing && this.resizeState.container) {
            this.updateResize(e);
        }
    }

    handlePointerMove(e) {
        e.preventDefault();
        if (this.isDragging && this.dragState.container) {
            this.updateDrag(e);
        } else if (this.isResizing && this.resizeState.container) {
            this.updateResize(e);
        }
    }

    handlePointerUp(e) {
        this.handleMouseUp(e);
    }

    updateDrag(e) {
        const { container, startX, startY, startLeft, startTop } = this.dragState;
        const deltaX = e.clientX - startX;
        const deltaY = e.clientY - startY;

        let newLeft = startLeft + deltaX;
        let newTop = startTop + deltaY;

        // Remove boundary constraints - windows can be moved anywhere
        container.style.left = `${newLeft}px`;
        container.style.top = `${newTop}px`;
    }

    updateResize(e) {
        const { container, startX, startY, startWidth, startHeight } = this.resizeState;
        const deltaX = e.clientX - startX;
        const deltaY = e.clientY - startY;

        let newWidth = Math.max(200, startWidth + deltaX);
        let newHeight = Math.max(150, startHeight + deltaY);

        // Remove boundary constraints - windows can be resized beyond viewport
        container.style.width = `${newWidth}px`;
        container.style.height = `${newHeight}px`;
    }

    handleMouseUp(e) {
        let element = null;

        // Clean up drag operation
        if (this.isDragging) {
            this.isDragging = false;
            if (this.dragState.container) {
                this.dragState.container.classList.remove('dragging');
            }
            element = this.dragState.element;
            this.dragState = {};
        }

        // Clean up resize operation
        if (this.isResizing) {
            this.isResizing = false;
            if (this.resizeState.container) {
                this.resizeState.container.classList.remove('resizing');
            }
            element = this.resizeState.element;
            this.resizeState = {};
        }

        // Remove all event listeners
        if (this.eventType === 'pointer' && element) {
            element.removeEventListener('pointermove', this.handlePointerMove);
            element.removeEventListener('pointerup', this.handlePointerUp);
            if (e && e.releasePointerCapture) {
                try {
                    element.releasePointerCapture(e.pointerId);
                } catch(err) {
                    // Ignore errors if pointer capture was already released
                }
            }
        } else {
            window.removeEventListener('mousemove', this.handleMouseMove, { capture: true });
            window.removeEventListener('mouseup', this.handleMouseUp, { capture: true });
        }

        // Remove overlay that blocks iframes
        this.removeOverlay();

        // Restore normal styles
        document.body.style.userSelect = '';
        document.body.style.overflow = '';

        if (element) {
            element.style.cursor = '';
        }

        // Reset event type
        this.eventType = null;
    }

    handleWindowResize() {
        // Remove window resize constraints - windows can remain outside viewport
        // Users can manage window positions manually
    }

    clearAll() {
        document.querySelectorAll('.iframe-container').forEach(el => el.remove());
        this.containers.clear();
        this.zIndexCounter = 100;
    }
}

const multiviewManager = new MultiviewManager();

function createIframes(ids, labels, urls) {
    multiviewManager.createIframes(ids, labels, urls);
}

function clearAll() {
    multiviewManager.clearAll();
}
