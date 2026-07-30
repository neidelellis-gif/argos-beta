"use strict";

const DAILY_POSITION_FIELDS = Object.freeze([
    "institution",
    "owner",
    "account",
    "asset_class",
    "asset_subclass",
    "asset_name",
    "identifier",
    "identifier_type",
    "quantity",
    "unit_price",
    "market_value",
    "currency",
    "portfolio_weight",
    "reference_date",
    "source_file"
]);

const DailyRequestBuilder = Object.freeze({
    build(canonicalPortfolioPositions) {
        return canonicalPortfolioPositions.map((position) => (
            Object.fromEntries(DAILY_POSITION_FIELDS.map((field) => (
                [field, position[field]]
            )))
        ));
    }
});

if (typeof globalThis !== "undefined") {
    globalThis.DailyRequestBuilder = DailyRequestBuilder;
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { DAILY_POSITION_FIELDS, DailyRequestBuilder };
}
