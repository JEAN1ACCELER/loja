document.addEventListener("DOMContentLoaded", () => {
    const menu = document.querySelector("#sidebar");
    document.querySelector("[data-menu-toggle]")?.addEventListener("click", () => {
        menu?.classList.toggle("open");
    });

    document.querySelectorAll(".flash-close").forEach((button) => {
        button.addEventListener("click", () => button.closest(".flash")?.remove());
    });

    document.querySelectorAll("form[data-confirm]").forEach((form) => {
        form.addEventListener("submit", (event) => {
            if (!window.confirm(form.dataset.confirm)) event.preventDefault();
        });
    });

    const date = document.querySelector("[data-date]");
    if (date) {
        date.textContent = new Intl.DateTimeFormat("pt-BR", {
            weekday: "short",
            day: "2-digit",
            month: "short",
            year: "numeric",
        }).format(new Date());
    }

    const items = document.querySelector("[data-sale-items]");
    const template = document.querySelector("[data-sale-row-template]");
    const total = document.querySelector("[data-sale-total]");
    const money = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
    const updateTotal = () => {
        if (!items || !total) return;
        const sum = [...items.querySelectorAll("[data-sale-row]")].reduce((carry, row) => {
            const selected = row.querySelector("[data-product-select]")?.selectedOptions[0];
            const price = Number(selected?.dataset.price || 0);
            const quantity = Number(row.querySelector("[data-quantity]")?.value || 0);
            return carry + price * quantity;
        }, 0);
        total.textContent = money.format(sum);
    };

    document.querySelector("[data-add-sale-row]")?.addEventListener("click", () => {
        if (!template || !items) return;
        items.append(template.content.cloneNode(true));
        updateTotal();
    });
    items?.addEventListener("input", updateTotal);
    items?.addEventListener("change", updateTotal);
    items?.addEventListener("click", (event) => {
        const button = event.target.closest("[data-remove-sale-row]");
        if (!button) return;
        const rows = items.querySelectorAll("[data-sale-row]");
        if (rows.length > 1) button.closest("[data-sale-row]")?.remove();
        else {
            const row = button.closest("[data-sale-row]");
            row.querySelector("[data-product-select]").value = "";
            row.querySelector("[data-quantity]").value = 1;
        }
        updateTotal();
    });

    document.querySelector("[data-sale-form]")?.addEventListener("submit", (event) => {
        if (!items) return;
        for (const row of items.querySelectorAll("[data-sale-row]")) {
            const selected = row.querySelector("[data-product-select]").selectedOptions[0];
            const quantity = Number(row.querySelector("[data-quantity]").value);
            const stock = Number(selected?.dataset.stock || 0);
            if (selected?.value && quantity > stock) {
                event.preventDefault();
                window.alert(`Estoque insuficiente. Disponível: ${stock} unidade(s).`);
                return;
            }
        }
    });
    updateTotal();
});
