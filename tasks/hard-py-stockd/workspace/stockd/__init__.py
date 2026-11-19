"""stockd: an event-sourced stock service for warehouses.

The event log in the data directory is the source of truth. The service keeps
the current stock in memory (the projection), writes snapshots of it, and on
start it loads the newest snapshot and replays the events after it.
"""

__version__ = "2.4.1"
