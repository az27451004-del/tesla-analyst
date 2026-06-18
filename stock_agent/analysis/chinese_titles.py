"""Deterministic Chinese title helpers for market events."""

from __future__ import annotations

from typing import Any


def chinese_event_title(title: str, driver: Any = "") -> str:
    """Return a stable Chinese reading title while preserving source text elsewhere."""
    lowered = title.lower()
    if looks_chinese(title):
        return title
    if "10-q" in lowered:
        return "季度财报披露：公司发布最新季度经营和财务报告"
    if "10-k" in lowered:
        return "年度报告披露：公司发布年度经营和财务报告"
    if "8-k" in lowered:
        return "重大事项披露：公司提交 8-K 临时报告"
    if "form 4" in lowered or lowered.startswith("4 filing") or "ownership" in lowered:
        return "内部人持股变动披露"
    if "form 144" in lowered or lowered.startswith("144 filing"):
        return "拟出售证券通知披露"
    if "fsd" in lowered or "full self-driving" in lowered:
        return _with_subject(title, "FSD 自动驾驶相关进展")
    if "robotaxi" in lowered:
        return _with_subject(title, "Robotaxi 自动驾驶出租车相关进展")
    if "ai chip" in lowered or "artificial intelligence" in lowered:
        return _with_subject(title, "AI 芯片或人工智能叙事进展")
    if "spacex" in lowered:
        return _with_subject(title, "SpaceX 相关叙事影响特斯拉估值")
    if "rating" in lowered or "price target" in lowered or "stock rating" in lowered:
        return _with_subject(title, "分析师评级或目标价变化")
    if "cathie wood" in lowered or "ark invest" in lowered:
        return _with_subject(title, "Cathie Wood/ARK 资金动向")
    if "ev growth" in lowered or "electric vehicle growth" in lowered:
        return _with_subject(title, "电动车行业增长放缓相关消息")
    if "support withdrawn" in lowered or "tax credit" in lowered or "subsidy" in lowered:
        return _with_subject(title, "补贴或政策支持变化")
    if "tariff" in lowered:
        return _with_subject(title, "关税政策变化")
    if "delivery" in lowered or "deliveries" in lowered:
        return _with_subject(title, "交付数据或交付预期变化")
    if "recall" in lowered or "investigation" in lowered or "nhtsa" in lowered:
        return _with_subject(title, "监管调查或召回风险")
    if str(driver) == "估值/安全边际":
        return _with_subject(title, "估值或评级相关消息")
    if str(driver) == "技术面/期权/资金流":
        return _with_subject(title, "资金流、持仓或技术面相关消息")
    return _with_subject(title, "相关财经新闻")


def looks_chinese(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def event_title_with_original(title: str, driver: Any = "") -> str:
    """Render Chinese title and keep English source title when it differs."""
    chinese = chinese_event_title(title, driver)
    if not title or chinese == title or looks_chinese(title):
        return chinese
    return f"{chinese}（英文原题：{title}）"


def translated_event_title(title: str, driver: Any = "") -> str:
    """Return a concise Chinese translation of the source title when possible."""
    if not title:
        return ""
    if looks_chinese(title):
        return title
    lowered = _normalize_title(title)
    exact = {
        "goldman sachs raises tesla stock delivery forecast on europe strength": "高盛因欧洲表现强劲上调特斯拉交付预测",
        "exclusive: tesla presented misleading full self-driving safety data to european regulators": "独家：特斯拉向欧洲监管机构提交了被指误导性的 FSD 安全数据",
        "dutch transportation minister defends tesla fsd approval": "荷兰交通部长为特斯拉 FSD 获批辩护",
        "why the tesla-spacex merger possibility makes sense rating upgrade": "为什么特斯拉与 SpaceX 合并的可能性有其逻辑（评级上调）",
        "tesla robotaxi concerns under texas sb 2807": "德州 SB 2807 法案下的特斯拉 Robotaxi 担忧",
        "tesla tsla stock after spacex ipo and new fsd approvals how the valuation story is shifting": "SpaceX IPO 与 FSD 新审批后，特斯拉估值叙事正在变化",
        "the latest way byd is topping tesla": "比亚迪最新在哪些方面领先特斯拉",
        "the battle of the musks: why cathie wood sold tesla stock to buy spacex": "马斯克相关资产之争：为什么 Cathie Wood 卖出特斯拉买入 SpaceX",
        "tesla may not exist in 5 years rating upgrade": "特斯拉五年后可能不复存在（评级上调）",
        "tsla stock falls senator raises concerns over teslas misleading fsd safety data": "TSLA 股价下跌，参议员质疑特斯拉 FSD 安全数据存在误导",
        "electric vehicle growth seen slowing after us support measures withdrawn": "美国支持措施撤回后，电动车增长被认为正在放缓",
        "elon is scared of this conversation democrat fires back at musks subsidy defense": "民主党人士反击马斯克的补贴辩护，称其回避这场讨论",
        "tesla stock cant escape spacexs gravity": "特斯拉股价难以摆脱 SpaceX 叙事的牵引",
        "tesla tsla stock gets fair value bump as analysts debate ai and demand": "分析师讨论 AI 与需求后，上调特斯拉公允价值判断",
        "tesla stock gains after spacexs historic debut": "SpaceX 历史性亮相后，特斯拉股价上涨",
        "tesla merger talk with spacex reshapes ai and investor outlook": "特斯拉与 SpaceX 合并讨论重塑 AI 与投资者预期",
        "teslas ai5 chip recently completed tape-out heres why this could be the most important development in the companys transition from automaker to ai giant": "特斯拉 AI5 芯片近期完成流片，可能成为其从车企转向 AI 巨头的重要进展",
        "tesla seeks customer backing to oppose new jersey driverless vehicle bills": "特斯拉寻求客户支持，反对新泽西无人驾驶车辆法案",
        "elon musk just delivered fantastic news for asml stock investors": "马斯克给 ASML 股票投资者带来利好消息",
        "spacex stock faces tesla-style crash fears as 3 trillion valuation sparks debate": "SpaceX 估值引发争议，市场担忧其股价可能出现特斯拉式回调",
    }.get(lowered)
    if exact:
        return exact
    return _generic_translation(title, driver)


def event_title_with_translation(title: str, driver: Any = "") -> str:
    """Render type summary plus translated source title for major-event sections."""
    chinese = chinese_event_title(title, driver)
    translated = translated_event_title(title, driver)
    if not translated or translated == chinese:
        return chinese
    return f"{chinese}｜{translated}"


def _with_subject(title: str, prefix: str) -> str:
    company = "特斯拉" if ("tesla" in title.lower() or "tsla" in title.lower()) else "相关公司"
    return f"{prefix}：{company}"


def _normalize_title(title: str) -> str:
    lowered = title.lower()
    lowered = lowered.replace("’", "'").replace("‘", "'").replace("–", "-").replace("—", "-")
    lowered = lowered.replace("'s", "s").replace("'", "")
    lowered = lowered.replace("u.s.", "us").replace("$", "")
    lowered = "".join(char if char.isalnum() or char in {" ", "-"} else " " for char in lowered)
    return " ".join(lowered.replace("-", "-").split())


def _generic_translation(title: str, driver: Any = "") -> str:
    lowered = title.lower()
    company = "特斯拉" if ("tesla" in lowered or "tsla" in lowered) else "相关公司"
    if "robotaxi" in lowered and ("concern" in lowered or "bill" in lowered):
        return f"{company} Robotaxi 面临监管或法案相关担忧"
    if "fsd" in lowered or "full self-driving" in lowered:
        if "misleading" in lowered or "concern" in lowered:
            return f"{company} FSD 安全数据或监管争议升温"
        if "approval" in lowered:
            return f"{company} FSD 获批或审批进展"
        return f"{company} FSD 自动驾驶相关进展"
    if "ai chip" in lowered:
        return f"{company} AI 芯片团队设定新目标"
    if "delivery" in lowered or "deliveries" in lowered:
        return f"{company}交付数据或交付预期变化"
    if "spacex" in lowered:
        return f"{company}与 SpaceX 相关叙事影响估值预期"
    if "subsidy" in lowered or "tax credit" in lowered or "support" in lowered:
        return f"{company}补贴或政策支持变化"
    if "rating" in lowered or "fair value" in lowered or "price target" in lowered:
        return f"{company}评级或估值观点变化"
    if "recall" in lowered or "investigation" in lowered or "nhtsa" in lowered:
        return f"{company}面临监管调查和召回风险"
    if str(driver) == "竞争格局":
        return f"{company}竞争格局相关变化"
    return chinese_event_title(title, driver)
