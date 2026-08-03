"use strict";

const ArgosAnalysisContext = (() => {
    const STORAGE_KEY = "argos.active-owner";

    const OWNERS = Object.freeze({
        nei_pf: Object.freeze({
            id: "nei_pf",
            name: "Nei",
            type: "PERSONAL",
            currency: "USD",
            institutions: Object.freeze([
                "Bradesco",
                "Ágora",
                "Monte Bravo",
                "Binance",
                "Bybit",
                "Coinbase"
            ])
        }),
        jolika: Object.freeze({
            id: "jolika",
            name: "Jolika",
            type: "COMPANY",
            currency: "USD",
            institutions: Object.freeze([
                "UBS",
                "Santander"
            ])
        })
    });

    let activeOwnerId = restoreOwnerId();

    function restoreOwnerId() {
        const storedOwnerId = window.localStorage.getItem(STORAGE_KEY);
        return Object.prototype.hasOwnProperty.call(OWNERS, storedOwnerId)
            ? storedOwnerId
            : "nei_pf";
    }

    function getOwners() {
        return Object.values(OWNERS).map((owner) => ({
            ...owner,
            institutions: [...owner.institutions]
        }));
    }

    function getActiveOwner() {
        const owner = OWNERS[activeOwnerId];
        return {
            ...owner,
            institutions: [...owner.institutions]
        };
    }

    function setActiveOwner(ownerId) {
        if (!Object.prototype.hasOwnProperty.call(OWNERS, ownerId)) {
            throw new RangeError("Titular inválido.");
        }

        activeOwnerId = ownerId;
        window.localStorage.setItem(STORAGE_KEY, ownerId);
        renderActiveOwner();

        window.dispatchEvent(new CustomEvent("argos:owner-change", {
            detail: { owner: getActiveOwner() }
        }));
    }

    function renderActiveOwner(root = document) {
        const owner = getActiveOwner();
        const selector = root.getElementById("activeOwnerSelector");
        const name = root.getElementById("activeOwnerName");

        if (selector) {
            selector.value = owner.id;
        }
        if (name) {
            name.textContent = owner.name;
        }

        root.documentElement.dataset.argosOwner = owner.id;
    }

    function setup(root = document) {
        const selector = root.getElementById("activeOwnerSelector");
        if (!selector) {
            return;
        }

        selector.replaceChildren();
        getOwners().forEach((owner) => {
            const option = root.createElement("option");
            option.value = owner.id;
            option.textContent = owner.name;
            selector.appendChild(option);
        });

        selector.addEventListener("change", () => {
            setActiveOwner(selector.value);
        });

        renderActiveOwner(root);
    }

    return Object.freeze({
        getOwners,
        getActiveOwner,
        setActiveOwner,
        setup
    });
})();

document.addEventListener("DOMContentLoaded", () => {
    ArgosAnalysisContext.setup();
});
