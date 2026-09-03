"""Domain service layer.

Contains pipeline logic (spatial ETL, deterministic hazard/vulnerability scoring,
risk/zoning/priority, and asynchronous DB synchronization). The services are
deliberately orchestrated but side-effect-free where practical, so they can be
unit tested against fixtures without a live database where possible.
"""
