"""Constants shared by the second-layer analysis package."""

DRIVER_DELIVERY = "交付/库存/价格"
DRIVER_FUNDAMENTAL = "毛利率/EPS/现金流"
DRIVER_NARRATIVE = "FSD/Robotaxi/AI"
DRIVER_MACRO = "利率/美元/纳指"
DRIVER_COMPETITION = "竞争格局"
DRIVER_REGULATORY = "监管/诉讼/政策"
DRIVER_ENERGY = "能源/供应链"
DRIVER_TECHNICAL = "技术面/期权/资金流"
DRIVER_VALUATION = "估值/安全边际"

DRIVERS = (
    DRIVER_DELIVERY,
    DRIVER_FUNDAMENTAL,
    DRIVER_NARRATIVE,
    DRIVER_MACRO,
    DRIVER_COMPETITION,
    DRIVER_REGULATORY,
    DRIVER_ENERGY,
    DRIVER_TECHNICAL,
    DRIVER_VALUATION,
)

POSITIVE_TERMS = {
    "beat",
    "beats",
    "record",
    "upgrade",
    "approval",
    "growth",
    "profit",
    "profitable",
    "strong demand",
    "cash flow",
}

NEGATIVE_TERMS = {
    "miss",
    "misses",
    "downgrade",
    "recall",
    "investigation",
    "lawsuit",
    "price cut",
    "weak demand",
    "delay",
    "loss",
    "tariff",
}
