"""One list of all tables, in the order they must be built / loaded."""
from tables import aggregates_yearly, country_ref, country_yearly, data_coverage, event_countries, events, global_monthly, global_yearly, gwp_constants

# CSV build order: a table comes after the tables it needs
BUILD_ORDER = [country_ref, global_monthly, country_yearly, aggregates_yearly, global_yearly, events, event_countries, gwp_constants, data_coverage]

# database order: parents before children (events before event_countries)
DB_ORDER = [global_monthly, global_yearly, country_yearly, country_ref, aggregates_yearly, gwp_constants, events, event_countries, data_coverage]