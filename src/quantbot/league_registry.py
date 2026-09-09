from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LeagueClassification:
    provider_league_id: int
    country: str
    league_name: str
    tier: int
    enabled: bool = True
    source: str = "API-Football provider league ID + project tier audit"


# API-Football v3 keeps league IDs stable across seasons. The provider fixture
# payload carries the league ID, but this registry also exposes an exact
# country/name index for older call sites that have not yet threaded the ID.
# Neither path infers tier from a league-name pattern: an entry must be present
# in this audited registry to be eligible.
_LEAGUES = (
    (39, "England", "Premier League", 1),
    (40, "England", "Championship", 2),
    (140, "Spain", "La Liga", 1),
    (141, "Spain", "Segunda Division", 2),
    (135, "Italy", "Serie A", 1),
    (136, "Italy", "Serie B", 2),
    (78, "Germany", "Bundesliga", 1),
    (79, "Germany", "2. Bundesliga", 2),
    (61, "France", "Ligue 1", 1),
    (62, "France", "Ligue 2", 2),
    (88, "Netherlands", "Eredivisie", 1),
    (89, "Netherlands", "Eerste Divisie", 2),
    (94, "Portugal", "Primeira Liga", 1),
    (95, "Portugal", "Segunda Liga", 2),
    (144, "Belgium", "Jupiler Pro League", 1),
    (145, "Belgium", "Challenger Pro League", 2),
    (179, "Scotland", "Premiership", 1),
    (180, "Scotland", "Championship", 2),
    (203, "Turkey", "Süper Lig", 1),
    (204, "Turkey", "1. Lig", 2),
    (197, "Greece", "Super League 1", 1),
    (198, "Greece", "Super League 2", 2),
    (218, "Austria", "Bundesliga", 1),
    (219, "Austria", "2. Liga", 2),
    (207, "Switzerland", "Super League", 1),
    (208, "Switzerland", "Challenge League", 2),
    (119, "Denmark", "Superliga", 1),
    (120, "Denmark", "1. Division", 2),
    (113, "Sweden", "Allsvenskan", 1),
    (114, "Sweden", "Superettan", 2),
    (103, "Norway", "Eliteserien", 1),
    (104, "Norway", "1. Division", 2),
    (106, "Poland", "Ekstraklasa", 1),
    (107, "Poland", "I Liga", 2),
    (345, "Czech-Republic", "Czech Liga", 1),
    (346, "Czech-Republic", "FNL", 2),
    (286, "Serbia", "Super Liga", 1),
    (287, "Serbia", "Prva Liga", 2),
    (283, "Romania", "Liga I", 1),
    (284, "Romania", "Liga II", 2),
    (172, "Bulgaria", "First League", 1),
    (173, "Bulgaria", "Second League", 2),
    (333, "Ukraine", "Premier League", 1),
    (334, "Ukraine", "Persha Liga", 2),
    (235, "Russia", "Premier League", 1),
    (236, "Russia", "First League", 2),
    (210, "Croatia", "HNL", 1),
    (211, "Croatia", "First NL", 2),
    (216, "Slovenia", "1. SNL", 1),
    (217, "Slovenia", "2. SNL", 2),
    (318, "Slovakia", "Super Liga", 1),
    (319, "Slovakia", "2. Liga", 2),
    (244, "Bosnia", "Premijer Liga", 1),
    (245, "Bosnia", "Prva Liga", 2),
    (71, "Brazil", "Serie A", 1),
    (72, "Brazil", "Serie B", 2),
    (128, "Argentina", "Liga Profesional", 1),
    (129, "Argentina", "Primera Nacional", 2),
    (239, "Colombia", "Primera A", 1),
    (240, "Colombia", "Primera B", 2),
    (265, "Chile", "Primera División", 1),
    (266, "Chile", "Primera B", 2),
    (242, "Ecuador", "Liga Pro", 1),
    (243, "Ecuador", "Liga Pro Serie B", 2),
    (281, "Peru", "Liga 1", 1),
    (282, "Peru", "Liga 2", 2),
    (268, "Uruguay", "Primera División", 1),
    (269, "Uruguay", "Segunda División", 2),
    (253, "USA", "Major League Soccer", 1),
    (254, "USA", "USL Championship", 2),
    (262, "Mexico", "Liga MX", 1),
    (263, "Mexico", "Liga de Expansión MX", 2),
    (98, "Japan", "J1 League", 1),
    (99, "Japan", "J2 League", 2),
    (292, "South-Korea", "K League 1", 1),
    (293, "South-Korea", "K League 2", 2),
    (188, "Australia", "A-League", 1),
    (169, "China", "Super League", 1),
    (170, "China", "League One", 2),
    (307, "Saudi-Arabia", "Pro League", 1),
    (308, "Saudi-Arabia", "Division 1", 2),
    (301, "United-Arab-Emirates", "Pro League", 1),
    (302, "United-Arab-Emirates", "Division 1", 2),
    (305, "Qatar", "Stars League", 1),
    (306, "Qatar", "QSL", 2),
    (384, "Israel", "Ligat Ha'al", 1),
    (385, "Israel", "Liga Leumit", 2),
    (233, "Egypt", "Premier League", 1),
    (234, "Egypt", "Second League", 2),
    (200, "Morocco", "Botola Pro", 1),
    (201, "Morocco", "Botola 2", 2),
)

REGISTRY: dict[int, LeagueClassification] = {
    league_id: LeagueClassification(league_id, country, name, tier)
    for league_id, country, name, tier in _LEAGUES
}
BY_COUNTRY_NAME: dict[tuple[str, str], LeagueClassification] = {
    (country.casefold(), name.casefold()): classification
    for classification in REGISTRY.values()
    for country, name in [(classification.country, classification.league_name)]
}

AFRICA_COUNTRIES = frozenset(
    {
        "algeria",
        "angola",
        "benin",
        "botswana",
        "burkina faso",
        "burundi",
        "cameroon",
        "cape verde islands",
        "central african republic",
        "chad",
        "comoros",
        "congo",
        "democratic republic of congo",
        "djibouti",
        "egypt",
        "equatorial guinea",
        "eritrea",
        "eswatini",
        "ethiopia",
        "gabon",
        "gambia",
        "ghana",
        "guinea",
        "guinea-bissau",
        "ivory coast",
        "kenya",
        "lesotho",
        "liberia",
        "libya",
        "madagascar",
        "malawi",
        "mali",
        "mauritania",
        "mauritius",
        "morocco",
        "mozambique",
        "namibia",
        "niger",
        "nigeria",
        "rwanda",
        "sao tome and principe",
        "senegal",
        "seychelles",
        "sierra leone",
        "somalia",
        "south africa",
        "south sudan",
        "sudan",
        "tanzania",
        "togo",
        "tunisia",
        "uganda",
        "zambia",
        "zimbabwe",
    }
)


def classification_for(league_id: int | None) -> LeagueClassification | None:
    if league_id is None:
        return None
    return REGISTRY.get(int(league_id))


def classification_for_fixture(
    league_id: int | None, country: str | None, league_name: str | None
) -> LeagueClassification | None:
    classification = classification_for(league_id)
    if classification is not None:
        return classification
    return BY_COUNTRY_NAME.get(
        ((country or "").casefold(), (league_name or "").casefold())
    )
