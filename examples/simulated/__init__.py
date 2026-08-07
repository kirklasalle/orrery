"""
Simulated adapters. **These perform no real work.**

They live here rather than in `orrery/adapters/` for one reason: nobody should import a
simulation by reflex while scanning the package for integrations. The installed package now
contains only adapters that touch the world — `FileSystemAdapter` and `ProcessAdapter`.

Each of these declares `is_simulation = True`, so the dispatcher warns on registration,
tags every receipt `simulated: True`, and refuses to register them at all unless
`adapters.allow_simulated` is switched on. They are useful for exercising the state machine
without side effects, and as worked examples of the adapter contract. They are not
integrations, and a benchmark run against them measures the state machine rather than
the world.
"""
