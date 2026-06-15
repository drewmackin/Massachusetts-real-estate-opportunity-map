#!/usr/bin/env python3
"""
Curated reference tables for criteria that have no clean per-town public feed.
Everything here is flagged dataQuality="curated" in the final output so the map
shows it as judgment-based, not measured. Names are matched loosely (case- and
suffix-insensitive) to the official TIGER municipality names in build_data.py.

Sources / basis:
  - Universities: institution locations (lat/lon) + a prestige "draw" weight.
  - Transit expansion: Green Line Extension (opened 2022) + South Coast Rail
    (Phase 1 service 2025-26).
  - Coastal / beach: MA oceanfront municipalities, tiered by beach destination value.
  - Vacation regions: Cape & Islands, Berkshires, Cape Ann, South Shore beaches.
  - Employer expansion: well-documented recent/ongoing major-employer growth hubs.
  - School tiers: broadly-documented DESE MCAS/accountability standing for the
    most house-price-relevant districts; unlisted towns default to neutral.
"""

# ---------------------------------------------------------------------------
# Top Massachusetts universities: (name, lat, lon, draw)
# draw: 3 = elite/national research draw, 2 = strong, 1 = regional
# ---------------------------------------------------------------------------
UNIVERSITIES = [
    ("Harvard University", 42.3770, -71.1167, 3),
    ("MIT", 42.3601, -71.0942, 3),
    ("Boston University", 42.3505, -71.1054, 3),
    ("Northeastern University", 42.3398, -71.0892, 3),
    ("Boston College", 42.3355, -71.1685, 3),
    ("Tufts University", 42.4075, -71.1190, 3),
    ("Brandeis University", 42.3654, -71.2597, 2),
    ("UMass Amherst", 42.3868, -72.5301, 3),
    ("UMass Lowell", 42.6540, -71.3250, 2),
    ("UMass Boston", 42.3138, -71.0383, 2),
    ("UMass Dartmouth", 41.6287, -70.9990, 1),
    ("Worcester Polytechnic Institute", 42.2746, -71.8063, 2),
    ("College of the Holy Cross", 42.2386, -71.8077, 2),
    ("Clark University", 42.2509, -71.8231, 1),
    ("Williams College", 42.7129, -73.2032, 3),
    ("Amherst College", 42.3709, -72.5170, 3),
    ("Smith College", 42.3185, -72.6406, 2),
    ("Mount Holyoke College", 42.2554, -72.5740, 2),
    ("Wellesley College", 42.2928, -71.3062, 3),
    ("Babson College", 42.2974, -71.2659, 2),
    ("Bentley University", 42.3893, -71.2204, 2),
    ("Olin College of Engineering", 42.2932, -71.2659, 2),
    ("Stonehill College", 42.0570, -71.0870, 1),
    ("Bridgewater State University", 41.9870, -70.9686, 1),
    ("Salem State University", 42.5037, -70.8870, 1),
    ("Framingham State University", 42.2954, -71.4360, 1),
    ("Worcester State University", 42.2710, -71.8430, 1),
    ("Westfield State University", 42.1290, -72.7570, 1),
    ("Fitchburg State University", 42.5840, -71.8090, 1),
    ("Endicott College", 42.5510, -70.8260, 1),
    ("Merrimack College", 42.6660, -71.1230, 1),
    ("Gordon College", 42.5910, -70.8810, 1),
    ("Hampshire College", 42.3260, -72.5300, 1),
    ("Assumption University", 42.2990, -71.8390, 1),
]

# ---------------------------------------------------------------------------
# Rail transit EXPANSION (recently opened / under construction) -> boosts transit
# ---------------------------------------------------------------------------
TRANSIT_EXPANSION = {
    # Green Line Extension (opened 2022)
    "Somerville": "Green Line Extension (opened 2022)",
    "Medford": "Green Line Extension (opened 2022)",
    # South Coast Rail Phase 1 (service 2025-26)
    "Fall River": "South Coast Rail (new service 2025-26)",
    "New Bedford": "South Coast Rail (new service 2025-26)",
    "Freetown": "South Coast Rail (new service 2025-26)",
    "Berkley": "On the South Coast Rail corridor (nearest station East Taunton)",
    "Taunton": "South Coast Rail (new service 2025-26)",
    "Lakeville": "South Coast Rail (Middleborough line upgrade)",
    "Middleborough": "South Coast Rail (new Middleborough station 2022)",
}

# ---------------------------------------------------------------------------
# Coastal / beach towns -> beach tier
# 3 = premier ocean-beach destination, 2 = oceanfront, 1 = harbor/bay/tidal river
# ---------------------------------------------------------------------------
COASTAL = {
    # Cape & Islands (premier)
    "Provincetown": 3, "Truro": 3, "Wellfleet": 3, "Eastham": 3, "Orleans": 3,
    "Chatham": 3, "Harwich": 3, "Dennis": 3, "Brewster": 3, "Yarmouth": 3,
    "Barnstable": 3, "Mashpee": 3, "Falmouth": 3, "Sandwich": 2, "Bourne": 2,
    "Nantucket": 3, "Edgartown": 3, "Oak Bluffs": 3, "Tisbury": 3,
    "West Tisbury": 2, "Chilmark": 3, "Aquinnah": 3, "Gosnold": 2,
    # North Shore / Cape Ann
    "Salisbury": 2, "Newburyport": 2, "Newbury": 2, "Rowley": 1, "Ipswich": 2,
    "Essex": 1, "Gloucester": 3, "Rockport": 3, "Manchester-by-the-Sea": 3, "Beverly": 2,
    "Salem": 1, "Marblehead": 2, "Swampscott": 2, "Nahant": 2, "Lynn": 1,
    "Revere": 2, "Winthrop": 2, "Saugus": 1,
    # South Shore
    "Hull": 2, "Cohasset": 2, "Scituate": 3, "Marshfield": 3, "Duxbury": 3,
    "Kingston": 1, "Plymouth": 2, "Hingham": 2, "Weymouth": 1, "Quincy": 1,
    # South Coast / Buzzards Bay
    "Wareham": 2, "Marion": 2, "Mattapoisett": 2, "Fairhaven": 2,
    "New Bedford": 1, "Dartmouth": 2, "Westport": 2, "Fall River": 1,
    "Boston": 1, "Chelsea": 1, "Everett": 1,
}

# ---------------------------------------------------------------------------
# Vacation / second-home regions -> seasonal-demand tier
# 3 = very high (islands, outer Cape, core Berkshires), 2 = high, 1 = moderate
# ---------------------------------------------------------------------------
VACATION = {
    # Cape Cod
    "Provincetown": 3, "Truro": 3, "Wellfleet": 3, "Eastham": 3, "Orleans": 3,
    "Chatham": 3, "Harwich": 2, "Dennis": 2, "Brewster": 2, "Yarmouth": 2,
    "Barnstable": 2, "Mashpee": 2, "Falmouth": 2, "Sandwich": 2, "Bourne": 1,
    # Islands
    "Nantucket": 3, "Edgartown": 3, "Oak Bluffs": 3, "Tisbury": 3,
    "West Tisbury": 3, "Chilmark": 3, "Aquinnah": 3, "Gosnold": 3,
    # Berkshires
    "Great Barrington": 3, "Stockbridge": 3, "Lenox": 3, "Lee": 2,
    "Williamstown": 2, "Becket": 2, "Otis": 2, "Monterey": 2, "Egremont": 2,
    "New Marlborough": 2, "Sandisfield": 1, "Tyringham": 2, "Mount Washington": 2,
    "Hancock": 2, "Sheffield": 1, "Richmond": 1, "West Stockbridge": 2,
    "Washington": 1, "Peru": 1, "Savoy": 1,
    # Cape Ann / North Shore beach
    "Rockport": 2, "Gloucester": 2, "Manchester-by-the-Sea": 2,
    # South Shore beach
    "Scituate": 1, "Marshfield": 1, "Duxbury": 1, "Plymouth": 1,
    # Western lakes / hilltowns
    "Wareham": 1,
}

# ---------------------------------------------------------------------------
# Major-employer expansion hubs -> tier (3 major hub, 2 notable, 1 emerging)
# ---------------------------------------------------------------------------
EMPLOYER = {
    "Cambridge": 3, "Boston": 3, "Somerville": 3, "Watertown": 2, "Waltham": 3,
    "Lexington": 2, "Bedford": 2, "Burlington": 2, "Billerica": 2, "Andover": 2,
    "Wilmington": 2, "Ayer": 1, "Shirley": 1, "Harvard": 1,
    "Framingham": 2, "Marlborough": 2, "Westborough": 2, "Southborough": 1,
    "Worcester": 2, "Norwood": 2, "Canton": 2, "Quincy": 2, "Lowell": 2,
    "New Bedford": 2, "Salem": 1, "Taunton": 1, "Plymouth": 1, "Needham": 2,
    "Westwood": 1, "Lincoln": 1, "Natick": 1, "Woburn": 1, "Tewksbury": 1,
    "Chelmsford": 1, "Mansfield": 1, "Foxborough": 1, "Braintree": 1,
}

# ---------------------------------------------------------------------------
# School reputation tiers (curated from DESE MCAS/accountability standing)
# 5 = top statewide, 4 = strong, 3 = solid/above avg, 2 = mixed, 1 = struggling.
# Unlisted towns default to neutral (treated as 3 with curated/low-confidence).
# Regional-district member towns share their district's tier.
# ---------------------------------------------------------------------------
SCHOOL_TIER = {
    # Elite (5)
    "Weston": 5, "Wellesley": 5, "Lexington": 5, "Concord": 5, "Carlisle": 5,
    "Lincoln": 5, "Dover": 5, "Sherborn": 5, "Wayland": 5, "Sudbury": 5,
    "Acton": 5, "Boxborough": 5, "Belmont": 5, "Winchester": 5, "Newton": 5,
    "Brookline": 5, "Needham": 5, "Westwood": 5, "Hopkinton": 5, "Southborough": 5,
    "Westborough": 5, "Harvard": 5, "Bolton": 5, "Stow": 5, "Hingham": 5,
    "Duxbury": 5, "Cohasset": 5, "Manchester-by-the-Sea": 5, "Hamilton": 5, "Wenham": 5,
    "Longmeadow": 5, "Andover": 5, "North Andover": 5, "Westford": 5, "Bedford": 5,
    # Strong (4)
    "Natick": 4, "Franklin": 4, "Medfield": 4, "Walpole": 4, "Norwell": 4,
    "Scituate": 4, "Marshfield": 4, "Pembroke": 4, "Hanover": 4, "Reading": 4,
    "North Reading": 4, "Wakefield": 4, "Melrose": 4, "Arlington": 4,
    "Lynnfield": 4, "Marblehead": 4, "Swampscott": 4, "Topsfield": 4,
    "Boxford": 4, "Georgetown": 4, "Ipswich": 4, "Sharon": 4, "Canton": 4,
    "Littleton": 4, "Groton": 4, "Pepperell": 4, "Holliston": 4,
    "Ashland": 4, "Shrewsbury": 4, "Grafton": 4, "Northborough": 4, "Mansfield": 4,
    "Foxborough": 4, "Easton": 4, "Bridgewater": 4, "East Longmeadow": 4,
    "Hampden": 4, "Wilbraham": 4, "Amherst": 4, "Northampton": 4, "Williamstown": 4,
    "Milton": 4, "Dedham": 4, "Hopedale": 4, "Mendon": 4, "Upton": 4,
    "Berlin": 4, "Boylston": 4, "West Boylston": 4, "Dennis": 4, "Yarmouth": 4,
    # Solid / above avg (3) -- many suburbs default here implicitly
    "Quincy": 3, "Braintree": 3, "Weymouth": 3, "Stoughton": 3, "Norton": 3,
    "Tewksbury": 3, "Billerica": 3, "Chelmsford": 3, "Wilmington": 3, "Woburn": 3,
    "Burlington": 3, "Stoneham": 3, "Saugus": 3, "Beverly": 3, "Danvers": 3,
    "Peabody": 3, "Salem": 3, "Gloucester": 3, "Plymouth": 3, "Kingston": 3,
    "Middleborough": 3, "Raynham": 3, "Dighton": 3, "Rehoboth": 3, "Seekonk": 3,
    "Attleboro": 3, "Auburn": 3, "Millbury": 3, "Sutton": 3, "Oxford": 3,
    "Leominster": 3, "Gardner": 3, "Westfield": 3, "Agawam": 3, "Ludlow": 3,
    "Chicopee": 3, "Pittsfield": 3, "Lenox": 3, "Lee": 3, "Great Barrington": 3,
    "Falmouth": 3, "Sandwich": 3, "Barnstable": 3, "Bourne": 3, "Mashpee": 3,
    "Framingham": 3, "Marlborough": 3, "Hudson": 3, "Maynard": 3, "Clinton": 3,
    "Taunton": 3, "Fairhaven": 3, "Dartmouth": 3, "Westport": 3, "Somerset": 3,
    "Medford": 3, "Watertown": 3, "Waltham": 3, "Revere": 3, "Malden": 3,
    "Everett": 3, "Cambridge": 3, "Somerville": 3, "Boston": 3,
    # Mixed / struggling (2 / 1) -- Gateway cities w/ documented challenges
    "Worcester": 2, "Lowell": 2, "Lawrence": 1, "Brockton": 2, "New Bedford": 2,
    "Fall River": 2, "Springfield": 1, "Holyoke": 1, "Chelsea": 2, "Lynn": 2,
    "Fitchburg": 2, "Haverhill": 2, "Methuen": 3, "Randolph": 2, "Southbridge": 2,
}


# ---------------------------------------------------------------------------
# Form of local government (curated from MA DLS / municipal charters).
# CITIES = municipalities operating under a CITY form of government (some are still
# legally styled "Town of ..."). COUNCIL_MANAGER = the subset (city or town) run by a
# professional manager/administrator rather than a strong mayor. REP_TOWN_MEETING =
# towns that use REPRESENTATIVE (elected town-meeting members) rather than open town
# meeting. Everything else defaults to OPEN town meeting + an elected select board.
# It's a general classification (labeled "curated") — the official site / Wikipedia
# link in the panel is authoritative for charter specifics.
# ---------------------------------------------------------------------------
CITIES = {
    "Agawam", "Amesbury", "Attleboro", "Barnstable", "Beverly", "Boston", "Braintree",
    "Brockton", "Cambridge", "Chelsea", "Chicopee", "Easthampton", "Everett",
    "Fall River", "Fitchburg", "Framingham", "Franklin", "Gardner", "Gloucester",
    "Greenfield", "Haverhill", "Holyoke", "Lawrence", "Leominster", "Lowell", "Lynn",
    "Malden", "Marlborough", "Medford", "Melrose", "Methuen", "New Bedford",
    "Newburyport", "Newton", "North Adams", "Northampton", "Palmer", "Peabody",
    "Pittsfield", "Quincy", "Randolph", "Revere", "Salem", "Somerville", "Southbridge",
    "Springfield", "Taunton", "Waltham", "Watertown", "West Springfield", "Westfield",
    "Weymouth", "Winthrop", "Woburn", "Worcester",
    # city-form municipalities that legally keep the "Town of" name (SecState list)
    "Bridgewater", "Amherst", "East Longmeadow",
}
COUNCIL_MANAGER = {  # professional manager/administrator instead of a strong mayor
    "Cambridge", "Worcester", "Lowell", "Chelsea", "Barnstable", "Watertown",
    "Southbridge", "Randolph", "Palmer", "Franklin", "Bridgewater", "Amherst",
    "Winthrop", "East Longmeadow", "North Attleborough",
}
# Representative (elected precinct members) town meeting — high-confidence only.
# Towns NOT listed default to OPEN town meeting, which is correct for the large
# majority (e.g. Andover, Marblehead, Tewksbury, Mansfield, Stoneham are open).
REP_TOWN_MEETING = {
    "Brookline", "Arlington", "Lexington", "Belmont", "Winchester", "Needham",
    "Dedham", "Plymouth", "Natick", "Milton", "Walpole", "Reading", "Wakefield",
    "Saugus", "Billerica", "Chelmsford", "Burlington", "Falmouth", "Norwood",
    "Adams", "Dartmouth",
}


def gov_form(name):
    """Return (form_label, kind) for a municipality. kind in {'city','town'}."""
    if name in COUNCIL_MANAGER and name in CITIES:
        return "City · Council–Manager", "city"
    if name in CITIES:
        return "City · Mayor & City Council", "city"
    if name in COUNCIL_MANAGER:           # town with a town council + manager
        return "Town · Town Council–Manager", "town"
    if name in REP_TOWN_MEETING:
        return "Town · Representative Town Meeting", "town"
    return "Town · Open Town Meeting & Select Board", "town"


def university_list():
    return UNIVERSITIES
