const dataTable = new TableManager("data");
const ignoredFields = Array("session", "key");

const priorityFields = ["id", "label", "page_order", "show_page", "started", "round", "group"];

let lastData, lastUpdate = 0;

function prioritizeFields(a, b) {
    const ai = priorityFields.indexOf(a[0]);
    const bi = priorityFields.indexOf(b[0]);

    if (ai !== -1 && bi !== -1) return ai - bi;  // both prioritized
    if (ai !== -1) return -1;                    // a is priority
    if (bi !== -1) return 1;                     // b is priority
    return a[0].localeCompare(b[0]);             // alphabetical for the rest
}

async function updateData() {
    [lastData, lastUpdate] = await uproot.invoke("viewdata", uproot.vars.sname, lastUpdate);

    for (const [uname, allfields] of Object.entries(lastData)) {
        dataTable.getCell(uname, "player").textContent = uname;

        for (const [field, payload] of Object.entries(allfields).sort(prioritizeFields)) {
            if (!field.startsWith("_uproot_") && !ignoredFields.includes(field)) {
                let herefield = document.createElement("span");

                herefield.title = `${epochToLocalISO(payload.time)} @ ${payload.context}`;
                herefield.classList.add("a-value");
                herefield.classList.add("me-2");

                if (payload.value_representation !== null) {
                    let rep = payload.value_representation;

                    if (rep.length > 28) {
                        herefield.textContent = `${rep.substr(0, 28)}…`;
                    }
                    else {
                        herefield.textContent = rep;
                    }
                }
                else {
                    herefield.classList.add("text-muted");
                    herefield.innerHTML = "<small>(deleted)</small>";
                }

                const details = document.createElement("div");
                const detailsHeader = document.createElement("h4");
                const detailsType = document.createElement("p");
                const detailsTypeActual = document.createElement("b");
                const detailsUpdate = document.createElement("p");
                const detailsUpdateActual = document.createElement("b");
                const detailsContent = document.createElement("textarea");

                detailsHeader.textContent = field;
                detailsType.innerHTML = `${_("Type")}: `;
                detailsTypeActual.textContent = payload.type_representation;
                detailsType.appendChild(detailsTypeActual);
                detailsUpdate.innerHTML = `${_("Last changed")}: `;
                detailsUpdateActual.textContent = herefield.title;
                detailsUpdate.appendChild(detailsUpdateActual);
                detailsContent.classList.add("form-control");
                detailsContent.disabled = true;
                detailsContent.rows = 8;
                detailsContent.textContent = payload.value_representation;

                details.appendChild(detailsHeader);
                details.appendChild(detailsType);
                details.appendChild(detailsUpdate);
                details.appendChild(detailsContent);

                herefield.onclick = () => {
                    uproot.alert(details.innerHTML);
                };

                dataTable.getCell(uname, field).innerHTML = "";
                dataTable.getCell(uname, field).appendChild(herefield);
            }
        }
    }
}

function refreshData(initial = false) {
    updateData().then(() => {
        if (initial) {
            dataTable._applySort("id", "asc");
        }
    });
}
