"""
The list of sources shown in the feed, in this order.
To add a site: write a Source class in this folder and add it here.
"""

from sources.davidson_science import DavidsonScience
from sources.inn_flashes import InnFlashes
from sources.nba import NbaScores
from sources.torah_portion import TorahPortion


def create_sources():
    return [InnFlashes(), NbaScores(), DavidsonScience(), TorahPortion()]
