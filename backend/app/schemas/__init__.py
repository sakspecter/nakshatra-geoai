"""Schema (API / DTO) layer package for Project Nakshatra.

Each module defines Pydantic v2 models that encode the API boundary contract. A
single hard rule threads through them all (Rule 2, Missing Data): a request or
response may only treat an absent measurement as *explicitly declared absent*
via a status field - never by silently defaulting the numeric value to 0/safe.
"""
