"""One list of all tables, in the order they must be built / loaded."""
from tables import table1, table2, table3, table4, table5, table6, table7, table8, table9

# CSV build order: a table comes after the tables it needs
BUILD_ORDER = [table4, table1, table3, table5, table2, table7, table8, table6, table9]

# database order: parents before children (events before event_countries)
DB_ORDER = [table1, table2, table3, table4, table5, table6, table7, table8, table9]