"use strict";

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
        return Boolean(payload)
            && payload.status === "SUCCESS"
            && typeof payload.generated_at === "string"
            && payload.header !== null
            && typeof payload.header === "object"
            && payload.message !== null
            && typeof payload.message === "object"
            && Array.isArray(payload.facts)
            && Array.isArray(payload.priorities)
            && Array.isArray(payload.analyses)
            && Array.isArray(payload.blocks)
            && payload.summary !== null
            && typeof payload.summary === "object"
            && payload.error === null;
    }
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { DailyFrontendClient };
}
