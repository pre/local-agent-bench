"""llm-eval with a memory guard that reads fake host files, for the tests that start llm-eval as a process.

$FAKE_HOST_DIR has card0/device/mem_info_gtt_used, card0/device/mem_info_gtt_total
and meminfo, in the format of /sys and /proc. The guard reads them each 0.05 s.
"""

import os
import sys
from functools import partial
from pathlib import Path

from llm_eval import cli, server
from llm_eval.sampler import read_gtt_total_mib, read_gtt_used_mib, read_mem_available_mib

host = Path(os.environ["FAKE_HOST_DIR"])
cli.open_server = partial(
    server.open_server,
    gtt_used=partial(read_gtt_used_mib, str(host / "card*/device/mem_info_gtt_used")),
    gtt_total=partial(read_gtt_total_mib, str(host / "card*/device/mem_info_gtt_total")),
    mem_available=partial(read_mem_available_mib, host / "meminfo"),
    guard_interval_s=0.05,
)

sys.exit(cli.main())
