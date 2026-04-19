# Copyright (c) Meta Platforms, Inc. and affiliates.
# Copyright (c) Last9, Inc.
from dataclasses import dataclass


@dataclass
class SinfoRow:
    """A row of sinfo output. Attributes should map directly to sinfo output field
    names. https://slurm.schedmd.com/sinfo.html#OPT_Format
    """

    nodelist: str
    gres: str
    gresused: str
    cpus: str
    cpusstate: str
    statelong: str
    partitionname: str
