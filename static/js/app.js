document.addEventListener("DOMContentLoaded", () => {
    setupFormValidation();
    setupDeleteConfirmation();
    setupPatientFilter();
    setupPatientSorting();
});

function setupFormValidation() {
    const form = document.getElementById("patient-form");
    if (!form) {
        return;
    }

    form.addEventListener("submit", (event) => {
        const requiredFields = form.querySelectorAll("input[required], textarea[required]");
        let hasError = false;

        requiredFields.forEach((field) => {
            const value = field.value.trim();
            if (!value) {
                hasError = true;
                field.style.borderColor = "#ff5f7a";
            } else {
                field.style.borderColor = "rgba(47, 198, 255, 0.25)";
            }
        });

        if (hasError) {
            event.preventDefault();
            alert("Completa todos los campos obligatorios antes de guardar.");
            return;
        }

        if (window.location.pathname.includes("register")) {
            alert("Paciente guardado correctamente.");
        }
    });
}

function setupDeleteConfirmation() {
    const forms = document.querySelectorAll(".delete-form");
    forms.forEach((form) => {
        form.addEventListener("submit", (event) => {
            const accepted = window.confirm("Esta acción eliminará el expediente. ¿Deseas continuar?");
            if (!accepted) {
                event.preventDefault();
            }
        });
    });
}

function setupPatientFilter() {
    const filterInput = document.getElementById("patient-filter");
    const table = document.getElementById("patients-table");
    if (!filterInput || !table) {
        return;
    }

    filterInput.addEventListener("input", () => {
        const term = filterInput.value.toLowerCase();
        const rows = table.querySelectorAll("tbody tr");

        rows.forEach((row) => {
            const name = row.querySelector("[data-key='name']")?.textContent?.toLowerCase() || "";
            const diagnosis = row.querySelector("[data-key='diagnosis']")?.textContent?.toLowerCase() || "";
            const visible = name.includes(term) || diagnosis.includes(term);
            row.style.display = visible ? "" : "none";
        });
    });
}

function setupPatientSorting() {
    const table = document.getElementById("patients-table");
    if (!table) {
        return;
    }

    const headers = table.querySelectorAll("th[data-sort]");
    const tbody = table.querySelector("tbody");

    headers.forEach((header) => {
        let asc = true;
        header.addEventListener("click", () => {
            const key = header.dataset.sort;
            const rows = Array.from(tbody.querySelectorAll("tr"));

            rows.sort((a, b) => {
                const left = (a.querySelector(`[data-key='${key}']`)?.textContent || "").trim();
                const right = (b.querySelector(`[data-key='${key}']`)?.textContent || "").trim();

                if (key === "age") {
                    return asc ? Number(left) - Number(right) : Number(right) - Number(left);
                }

                if (key === "consultation_date") {
                    return asc
                        ? new Date(left).getTime() - new Date(right).getTime()
                        : new Date(right).getTime() - new Date(left).getTime();
                }

                return asc ? left.localeCompare(right) : right.localeCompare(left);
            });

            rows.forEach((row) => tbody.appendChild(row));
            asc = !asc;
        });
    });
}
