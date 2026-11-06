VENUE_ALIASE = {
    "L'Anti Bar": [
        "L'Anti Bar",
        "L'Anti Bar & Spectacles"
    ],
    "Club Soda": [
        "Club Soda",
        "CLUB SODA"
    ],
    "HISTORY": [
        "History",
        "HISTORY",
        "History Toronto"
    ],
    "Salle Montaigne": [
        "Salle Montaigne",
        "Salle Montaigne - Cégep Limoilou"
    ],
    "Salle Wilfrid-Pelletier": [
        "Salle Wilfrid-Pelletier",
        "Salle Wilfrid-Pelletier - PN",
        "Wilfrid-Pelletier"
    ],
    "The Theatre at Great Canadian": [
        "The Theatre at Great Canadian",
        "The Theatre at Great Canadian Toronto"
    ],
}

VENUE_CITY = {
    "Centre Bell": "Montreal",
    "Club Soda": "Montreal",
    "Fairmount Theatre": "Montreal",
    "Le Ministère": "Montreal",
    "MTELUS": "Montreal",
    "L'Olympia": "Montreal", 
    "Petit Campus": "Montreal",
    "Piranha Bar": "Montreal",
    "Place Bell": "Montreal", 
    "Salle Wilfrid-Pelletier": "Montreal",
    "Le Studio TD": "Montreal",
    "Théâtre Beanfield": "Montreal",
    "Théâtre Paradoxe": "Montreal",

    "The Bronson": "Ottawa",
    "History Ottawa": "Ottawa",
    "Overflow Brewery": "Ottawa",
    "Rainbow Bistro": "Ottawa",
    "Salle Odyssée": "Ottawa",

    "L'Anti Bar": "Quebec",
    "L'Impérial": "Quebec",
    "Salle Montaigne" : "Quebec", 
    "La Source de la Martinière": "Quebec",
    "Studio Sonum": "Quebec",
    "Théâtre Capitole": "Quebec",

    "Coca-Cola Coliseum": "Toronto",
    "The Concert Hall": "Toronto",
    "The Danforth Music Hall": "Toronto",
    "Hard Luck Bar": "Toronto",
    "HISTORY": "Toronto",
    "Lee's Palace": "Toronto",
    "The Opera House": "Toronto",
    "RBC Amphitheatre": "Toronto",
    "REBEL": "Toronto",
    "Sneaky Dee's": "Toronto",
    "The Phoenix Concert Theatre": "Toronto",
    "The Theatre at Great Canadian": "Toronto",
}

# ---------------------------------------------------------------------------
# Fallback lookup that ignores case, accents and punctuation. It is only used
# when the exact name is not found, so names that match today behave the same.
# ---------------------------------------------------------------------------
def _norm(name):
    s = unicodedata.normalize("NFKD", str(name or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


_NORM_INDEX = {}
for _venue, _city in VENUE_CITY.items():
    _NORM_INDEX[_norm(_venue)] = _city
for _canonical, _aliases in VENUE_ALIASE.items():
    if _canonical in VENUE_CITY:
        for _alias in _aliases:
            _NORM_INDEX.setdefault(_norm(_alias), VENUE_CITY[_canonical])


class _VenueCity(dict):
    def get(self, key, default=None):
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        return _NORM_INDEX.get(_norm(key), default)

    def __missing__(self, key):
        found = _NORM_INDEX.get(_norm(key))
        if found is None:
            raise KeyError(key)
        return found

VENUE_CITY = _VenueCity(VENUE_CITY)
