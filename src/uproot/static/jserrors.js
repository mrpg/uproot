const jserrorsTarget = `${uproot.vars._uproot_internal.root}/jserrors/`;

function isConsoleError(source, stack) {
    const consolePatterns = [
        'debugger eval code',
        '<anonymous>',
        'eval at <anonymous>',
        'VM\\d+:',
        'console.log',
        'console.error',
        'console.warn'
    ];
    
    const sourceStr = String(source || '');
    const stackStr = String(stack || '');
    
    return consolePatterns.some(pattern => 
        new RegExp(pattern).test(sourceStr) || new RegExp(pattern).test(stackStr)
    );
}

function jserrorsSend(message, source = "unknown", lineno = "?", colno = "?", stack = "") {
    if (isConsoleError(source, stack)) return;
    
    const timestamp = new Date().toISOString();
    const locationInfo = source ? ` [${source}:${lineno}:${colno}]` : "";

    return uproot.api("jserrors", `${message}${locationInfo}`);
}

function jserrorsLocation(stack) {
    const stackLines = stack.split('\n');
    if (stackLines.length < 2) return {};

    const fileLineMatch = stackLines.find(line => 
        line.includes('.js:') || line.includes('.mjs:') || line.includes('.jsx:')
    );

    if (!fileLineMatch) return {};

    const matches = fileLineMatch.match(/\((.*?):(\d+):(\d+)\)/) || 
        fileLineMatch.match(/(.*?):(\d+):(\d+)/);

    if (!matches) return {};

    return {
        source: matches[1],
        line: matches[2],
        column: matches[3],
    };
}

window.onerror = (message, source, lineno, colno, error) => {
    const stack = error ? error.stack : '';

    jserrorsSend(`Global error: ${message}`, source, lineno, colno, stack);

    return false;
};

window.addEventListener("unhandledrejection", (event) => {
    const error = event.reason;
    const stack = error instanceof Error ? error.stack : '';
    const errorLocation = stack ? jserrorsLocation(stack) : {};

    jserrorsSend(
        `Unhandled promise rejection: ${event.reason}`,
        errorLocation.source,
        errorLocation.line,
        errorLocation.column,
        stack,
    );
});

window.addEventListener("error", (event) => {
    const stack = event.error ? event.error.stack : '';

    jserrorsSend(
        `Error event: ${event.message}`,
        event.filename,
        event.lineno,
        event.colno,
        stack,
    );
});
