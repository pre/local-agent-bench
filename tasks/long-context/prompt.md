The provisioning pipeline will start to use `addrplan` for new nodes next month. The package was written against revision 11 of our network and node addressing standard, and nobody has checked it since. The current standard is revision 14, in `docs/network-standard.md`.

Please review `addrplan/plan.py` against revision 14 and correct each value that does not agree with it, for all sites and racks that the standard covers. Some things to keep in mind:

- The standard is the authority. Do not change `docs/network-standard.md`.
- Keep the names and signatures of the public functions in `addrplan/plan.py`, because the pipeline imports them, and keep the output format of `node_plan`.
- The tests in `tests/` were written together with the code, so they can be wrong as well. Update them to the standard.
- Set `STANDARD_REVISION` in `addrplan/__init__.py` to 14 when you are done.

When you finish, give me a short list of what you changed and the rule number in the standard for each change.
