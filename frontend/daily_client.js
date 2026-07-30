"use strict";

const DailyApiContract = Object.freeze({
    version: "1.2",
    compatibleVersions: Object.freeze(["1.0", "1.1", "1.2"]),
    statuses: Object.freeze(["SUCCESS", "ERROR"]),
    experienceStatuses: Object.freeze([
        "READY", "NO_ACTION_REQUIRED", "ATTENTION_REQUIRED", "DECISION_REQUIRED"
    ]),
    priorityLevels: Object.freeze(["HIGH", "MEDIUM", "LOW"]),
    blockTypes: Object.freeze(["FACTS", "PRIORITIES", "ANALYSES"]),
    requiredResponseFields: Object.freeze([
        "status", "generated_at", "contract_version", "experience_status",
        "header", "message", "facts", "priorities", "analyses", "blocks",
        "summary", "error"
    ]),

    isCompatibleResponse(payload) {
        if (!payload || typeof payload !== "object"
                || !this.requiredResponseFields.every((field) => (
                    Object.prototype.hasOwnProperty.call(payload, field)
                ))
                || !this.compatibleVersions.includes(payload.contract_version)
                || !this.statuses.includes(payload.status)) {
            return false;
        }
        if (payload.status === "ERROR") {
            return payload.error !== null && typeof payload.error === "object";
        }
        return typeof payload.generated_at === "string"
            && this.experienceStatuses.includes(payload.experience_status)
            && payload.header !== null && typeof payload.header === "object"
            && payload.message !== null && typeof payload.message === "object"
            && [payload.facts, payload.priorities, payload.analyses, payload.blocks]
                .every(Array.isArray)
            && (payload.contract_version === "1.0" || Array.isArray(payload.market_agenda))
            && (payload.contract_version !== "1.2" || Array.isArray(payload.impact_assessments))
            && payload.facts.every((fact) => fact && typeof fact === "object"
                && this.priorityLevels.includes(fact.importance))
            && payload.priorities.every((priority) => (
                priority && typeof priority === "object"
                && this.priorityLevels.includes(priority.level)
            ))
            && payload.blocks.every((block) => block && typeof block === "object"
                && this.blockTypes.includes(block.type))
            && payload.summary !== null && typeof payload.summary === "object"
            && payload.error === null;
    }
});

class DailyFrontendClient {
    constructor(fetchImplementation = fetch) {
        this.fetch = fetchImplementation;
    }

    async loadExperience(request) {
        let response;
        try {
            response = await this.fetch("/api/daily-experience", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(request)
            });
        } catch (error) {
            throw new Error("Não foi possível carregar a experiência diária.");
        }

        let payload;
        try {
            payload = await response.json();
        } catch (error) {
            throw new Error("Erro interno.");
        }

        if (response.status !== 200) {
            throw new Error(payload && payload.error && payload.error.message
                ? payload.error.message
                : "Erro interno.");
        }
        if (!DailyFrontendClient.isDailyApiResponse(payload)) {
            throw new Error("Erro interno.");
        }
        return payload;
    }

    static isDailyApiResponse(payload) {
        return payload && payload.status === "SUCCESS"
            && DailyApiContract.isCompatibleResponse(payload);
    }
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { DailyApiContract, DailyFrontendClient };
}
